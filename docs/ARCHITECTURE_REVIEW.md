# Architecture Review & Hardening Plan

A critical read of the current architecture against what a production system of
this shape is expected to do. It answers four questions an evaluator (or a
future on-call engineer) will ask:

1. **Does the architecture follow industry standards?** — what we get right, and where we fall short.
2. **What is the security issue?** — the one real gap behind the strong-looking guard, and how to close it.
3. **How are performance drops handled?** — where latency/throughput degrade, what already protects us, what doesn't.
4. **How do we stop an agent stuck in a loop, and how do we prevent it?** — current bounds, their blind spots, the fix.

> **Scope note.** This document is the *plan*. It is written before any of the
> remediation code so the design can be reviewed first; each fix below is marked
> **(planned)** and cross-references the exact file it will touch. Nothing in the
> running system changes by reading this.

Companion docs: [ARCHITECTURE.md](ARCHITECTURE.md) (how it's built today),
[DECISIONS.md](DECISIONS.md) (why), [SCALING.md] *(planned, Phase 6)*.

---

## 1. Industry-standard scorecard

The core design is sound and follows the patterns you'd expect. The gaps are all
at the **operational boundary** (identity, limits, observability), not in the
data path.

| Area | Standard expectation | Status | Evidence |
|---|---|---|---|
| Layering / separation | API ↔ service ↔ data layers, no leaks | ✅ Followed | `api/` · `services/` · `db/` · `agent/` · `guards/` |
| LLM safety boundary | Model never touches raw data; retrieval is bounded | ✅ Followed | LLM only writes SQL and reads ≤200 aggregated rows ([ARCHITECTURE.md §1](ARCHITECTURE.md)) |
| SQL injection defense | Parameterized queries; parser-based validation (not regex) | ✅ Followed | [api/filters.py](../backend/api/filters.py) binds params; [guards/sql_validator.py](../backend/guards/sql_validator.py) uses `sqlglot` |
| Read-only data access | Agent SQL runs read-only | ⚠️ Partial | `SET TRANSACTION READ ONLY` is set ([db/session.py:47](../backend/db/session.py#L47)) **but on a privileged connection** — see §2 |
| Least-privilege identity | Dedicated low-privilege DB role for agent queries | ❌ Missing | `DATABASE_URL_READONLY` defined but **empty and unused** ([config.py:11](../backend/app/config.py#L11)) |
| Bounded execution | Statement timeout + row cap + single statement | ✅ Followed | `statement_timeout` ([sql.py:54-57](../backend/agent/nodes/sql.py#L54)); enforced `LIMIT` ([sql_validator.py:159-169](../backend/guards/sql_validator.py#L159)) |
| Retry / graceful failure | Bounded retries, degrade don't crash | ✅ Followed | `MAX_RETRIES=3` + `fail` node ([graph.py:19-28](../backend/agent/graph.py#L19)); LLM stub fallback ([llm.py](../backend/agent/llm.py)) |
| Caching | Keyed, TTL'd, swappable backend | ✅ Followed (in-proc) | `hash(sql+params)` TTL cache ([cache.py](../backend/services/cache.py)) |
| Connection pooling | Pooled, pre-pinged | ✅ Followed | `pool_size=5, max_overflow=5, pool_pre_ping` ([session.py:24-31](../backend/db/session.py#L24)) |
| Config / secrets | Env-driven, secrets git-ignored | ✅ Followed | `pydantic-settings`; `.env` ignored, only `.env.example` committed |
| Rate limiting / quota budget | Protect against upstream (LLM) limits & abuse | ❌ Missing | No budget/backoff — see §3 (this is what caused the live `429`) |
| AuthN / AuthZ | API requires identity; CORS scoped | ❌ Missing | Endpoints are open; CORS permissive ([app/main.py](../backend/app/main.py)) |
| Observability | Structured logs, request IDs, tracing, token/latency metrics | ⚠️ Partial | `logging.warning` only; no request IDs, traces, or metrics |
| Horizontal scalability | No process-local state on the request path | ⚠️ Partial | Report store and cache are **in-process** ([report_builder.py](../backend/services/report_builder.py), cache.py) |
| Test isolation | Deterministic; no live third-party calls | ❌ Missing | Report tests hit the **live** LLM — flaky, and it drained the Gemini daily quota |

**Verdict.** The *data path* meets the bar: the LLM is boxed, SQL is parsed and
whitelisted, execution is read-only and bounded. The *operational envelope* is
dev-grade: single DB identity, no quota/auth/observability, process-local state.
That is the expected shape for a screening project — the point of this document
is to name each gap and show the fix is understood.

---

## 2. The security issue

### The guard is strong — but it is defense-in-depth, not the outer boundary

[guards/sql_validator.py](../backend/guards/sql_validator.py) is genuinely good:
it parses with `sqlglot` (not regex), rejects anything that isn't
`SELECT`/`WITH`/set-op, walks the tree for forbidden nodes
(`INSERT/UPDATE/DELETE/DROP/CREATE/ALTER/SET/INTO/MERGE/…`), whitelists tables
**and** columns, blocks cross-database references, strips comments, and forces a
`LIMIT`. It then executes the **re-serialized** canonical SQL, not the raw string.

**The gap:** every query — dashboard *and* agent-authored — runs over the single
`DATABASE_URL` connection ([session.py:24](../backend/db/session.py#L24)), which
is almost certainly a privileged/admin account. The only thing stopping a write
is (a) the guard and (b) `SET TRANSACTION READ ONLY`. Both are **in-process
software checks**. The database itself would happily let that account write.

Why that matters — the realistic failure mode is a **parser differential**:
`sqlglot` parses in its `postgres` dialect, but the statement actually executes on
**CockroachDB**, whose grammar and functions differ (see CLAUDE.md's own warning
to test Cockroach behavior). Any construct that `sqlglot` normalizes or tolerates
differently than Cockroach executes is a candidate to slip through the guard
while doing something unintended at runtime. When the guard is the *only* barrier,
one such differential is a breach. With a least-privilege role behind it, the same
differential is a failed query.

### Secondary issues (lower severity)

- **No authN/authZ + permissive CORS:** anyone who can reach the API can drive the
  agent and generate load/cost. Fine on localhost, not for any shared deployment.
- **Unbounded chat input:** `ChatRequest.message` has no length cap
  ([chat.py:37](../backend/api/chat.py#L37)); a huge prompt is a cost/DoS vector.
  Prompt-injection *content* is handled (system prompts instruct the model to
  ignore rule-changes, and the guard is the real enforcement), but size is not.
- **Secrets in plaintext env:** acceptable for dev; production should use a secret
  manager, not a file.

### Fix plan (planned)

1. **Provision a read-only DB role** and wire `DATABASE_URL_READONLY`
   ([config.py](../backend/app/config.py)) into a second engine used by
   `read_only_session` for *all* agent/report SQL. `GRANT SELECT` on `mart.*` /
   `olist.*` only; no `INSERT/UPDATE/DELETE/DDL`. This makes read-only a
   **database-enforced** guarantee, demoting the guard to defense-in-depth where
   it belongs. *Touches:* `db/session.py`, `app/config.py`.
2. **Add a message length cap** (e.g. 2–4 KB) and reject oversized input at the
   API edge. *Touches:* `api/chat.py`.
3. **Gate the API** behind a simple API key / token and scope CORS to known
   origins before any non-local deployment. *Touches:* `app/main.py`.

---

## 3. Performance-drop handling

### Where performance actually degrades

| Source | Effect | Today's mitigation | Gap |
|---|---|---|---|
| LLM latency | Multi-second per call | Streaming status events keep the UI responsive ([chat.py](../backend/api/chat.py)) | No per-call timeout — a hung call blocks the request (see §4) |
| **LLM quota / 429** | Requests fail upstream | Graceful fallback to the deterministic stub ([llm.py:67-69](../backend/agent/llm.py#L67)) | No backoff, no budget, no user-visible "degraded" signal — this is what we hit |
| **Report call amplification** | One report = outline + N×(SQL + chart-spec + narrative) + summary | Custom sections capped (`_MAX_CUSTOM=3`) | Still ~8–15 LLM calls per report — the dominant latency **and** quota cost |
| Cold cache / heavy query | First hit slow | TTL cache + pre-aggregated `mart.*` + indexes | Cache is per-process; no shared cache across workers |
| Large result set | Payload/parse cost | `LIMIT`≤200 enforced; chat rows capped at 60 | — |
| Connection pool exhaustion | Requests queue | `pool_size=5 + max_overflow=5`, `pool_pre_ping` | Sync endpoints run in the threadpool; no async DB |

### What already protects us (and is correct)

- **Pre-aggregation:** `mart.*` tables + indexes mean dashboard queries touch
  rollups, not raw rows ([ARCHITECTURE.md §3](ARCHITECTURE.md)).
- **TTL cache** keyed by `hash(sql+params)` collapses repeat loads
  ([cache.py](../backend/services/cache.py)); per-chart insights are cached too.
- **Statement timeout** bounds any single query ([sql.py:54](../backend/agent/nodes/sql.py#L54)).
- **Graceful degradation:** when the LLM is unavailable the whole graph still runs
  on the stub, so the product never hard-fails on an upstream outage.

### Fix plan (planned)

1. **Quota resilience:** wrap LLM calls with bounded **retry + exponential
   backoff with jitter** on `429/503`, and a short **circuit breaker** so a
   quota-exhausted model trips straight to the stub for a cooldown instead of
   retrying each call. Surface a `degraded: true` flag in responses so the UI can
   say "AI summaries temporarily unavailable". *Touches:* `agent/llm.py`.
2. **Cut report amplification:** batch the per-section narratives into fewer
   calls (or make them concurrent with a bounded worker pool), and cache narrative
   text by `hash(section + facts)`. *Touches:* `services/report_builder.py`.
3. **Deterministic tests:** stub the LLM in `tests/test_reports.py` (as
   `test_agent_graph.py` already does) so CI never makes live calls — this removes
   the flakiness *and* the quota drain that first surfaced the `429`.
4. **Phase 6 scaling work (already planned):** benchmark at current size and ~1M
   rows, record numbers in `SCALING.md`, and move the cache + report store behind
   Redis/object storage for multi-worker deployments. *Touches:* `scripts/benchmark.py`, `services/cache.py`, `services/report_builder.py`.

---

## 4. Stopping (and preventing) a stuck agent

### How the agent is bounded today

The graph has **two** retry loops — validator→generator and executor→generator —
and both share one bound:

- A single `retries` counter in `AgentState` ([state.py:27](../backend/agent/state.py#L27)),
  incremented on every validation/execution failure
  ([sql.py:49,63](../backend/agent/nodes/sql.py#L49)).
- Conditional edges send flow back to the generator only while
  `retries < MAX_RETRIES (3)`, otherwise to the `fail` node → `END`
  ([graph.py:19-28](../backend/agent/graph.py#L19)).
- LangGraph's own **`recursion_limit`** (default **25** steps) is the backstop if
  that counter logic ever regressed — the run raises `GraphRecursionError` rather
  than spinning forever.

So a *graph-step* loop is already well bounded: at most 3 regeneration attempts,
then a graceful failure answer. This is the right pattern.

### The blind spots

1. **No wall-clock deadline.** The bounds count *steps*, not *time*. If a single
   LLM call hangs on the network, the request blocks indefinitely — the step
   counter never advances because the node never returns. There is **no timeout on
   the LLM client** ([llm.py](../backend/agent/llm.py) uses the SDK default).
2. **No cancellation on client disconnect.** The chat stream iterates
   `agent.stream(...)` to completion ([chat.py:66](../backend/api/chat.py#L66));
   if the browser closes, the server keeps working (and keeps spending LLM calls).
3. **`recursion_limit` is implicit.** We rely on the default 25; it isn't set
   explicitly in `ask`/`stream` ([graph.py:89-93](../backend/agent/graph.py#L89)),
   so the intended ceiling isn't visible or tuned.
4. **The report path is outside the retry/guard loop.** `build_report` makes its
   own LLM + SQL calls directly ([report_builder.py](../backend/services/report_builder.py)),
   so none of the graph's loop-bounding applies there — its safety comes only from
   per-call try/except and the single `validate_sql` check.

### How to stop a stuck agent — now vs. planned

**With the code as-is:**
- Graph-level loops self-terminate (3 retries → `fail`, or `GraphRecursionError`
  at 25 steps).
- A hung *LLM call* cannot be stopped gracefully today — the only recourse is to
  kill/restart the worker process. That is the honest current answer, and it is
  the gap the fixes below close.

**Fix plan (planned):**
1. **Per-call LLM timeout.** Pass a request timeout to the Gemini client
   (e.g. 15–30 s) so a hung call fails fast and routes to the stub fallback that
   already exists. *Touches:* `agent/llm.py`.
2. **Whole-run deadline.** Run `agent.invoke/stream` under an overall wall-clock
   budget (e.g. 60 s); on expiry, emit a graceful timeout answer instead of
   hanging. *Touches:* `agent/graph.py`, `api/chat.py`.
3. **Explicit `recursion_limit`.** Set it in the run config
   (`{"recursion_limit": 12, "configurable": {...}}`) so the intended ceiling is
   declared and tuned, not inherited. *Touches:* `agent/graph.py`.
4. **Honor client disconnect.** Detect `request.is_disconnected()` in the SSE loop
   and stop iterating, so a closed tab stops spending work/quota. *Touches:* `api/chat.py`.

### How to prevent it recurring

- **Total-attempt budget, not per-loop:** the shared `retries` counter already
  means validation + execution attempts can't jointly exceed 3 — keep it shared.
- **Deterministic failure is a feature:** the `fail` node must always produce a
  user-facing answer; every new branch must terminate at `END`. Add a test that
  asserts the graph has no node without a path to `END`.
- **Oscillation guard:** on each retry the generator is re-fed the previous SQL +
  error ([sql.py:37-38](../backend/agent/nodes/sql.py#L37)); if it returns an
  identical proposal twice, short-circuit to `fail` rather than burning the last
  retry on the same string. *(planned)*
- **Keep timeouts layered:** per-call (LLM, DB `statement_timeout`) **and**
  per-run (wall clock) **and** per-graph (`recursion_limit`) — three independent
  ceilings so no single failure mode can hang the system.

---

## 5. Prioritized remediation backlog

Ordered by risk-reduction per unit of effort.

| # | Fix | Why first | Effort | Status | File(s) |
|---|---|---|---|---|---|
| 1 | Deterministic LLM stub in report tests | Stops flakiness **and** quota drain immediately; unblocks CI | S | ✅ done | `tests/test_reports.py` |
| 2 | Per-call LLM timeout + 429 breaker/backoff + `degraded` flag | Removes the only un-stoppable hang; makes quota failures graceful | M | ✅ done | `agent/llm.py` |
| 3 | Explicit `recursion_limit` + input cap + disconnect | Closes the loop/hang blind spots | M | ⚠️ partial — `recursion_limit` + input cap done; whole-run wall-clock deadline still planned | `agent/graph.py`, `api/chat.py` |
| 4 | Read-only DB role via `DATABASE_URL_READONLY` | Turns read-only into a DB-enforced guarantee (true outer boundary) | M | ⬜ planned (needs a DB role provisioned) | `db/session.py`, `app/config.py` |
| 5 | Chat input cap + API gate + scoped CORS | Basic abuse/cost protection before any shared deploy | S–M | ⚠️ partial — input cap done; CORS already scoped to localhost; API gate planned | `api/chat.py`, `app/main.py` |
| 6 | Report call batching/concurrency + narrative cache | Biggest latency & quota win for reports | M | ⬜ planned | `services/report_builder.py` |
| 7 | Benchmarks + externalized cache/report store | Phase 6 scaling; proves the numbers | L | ⬜ planned | `scripts/benchmark.py`, `services/cache.py`, `services/report_builder.py` |

### What shipped in this pass

- **LLM client** ([agent/llm.py](../backend/agent/llm.py)): a 30 s per-call request
  timeout; a quota (`429`) circuit breaker that serves the deterministic stub for
  a 300 s cooldown instead of hammering; short backoff retries on transient
  `503`s; and a `degraded` signal exposed via `llm_degraded()`.
- **Loop control** ([agent/graph.py](../backend/agent/graph.py)): an explicit
  `recursion_limit = 12` applied to every run through a shared `run_config()`.
- **API edge** ([api/chat.py](../backend/api/chat.py)): chat `message` capped at
  4000 chars, and a `degraded` flag in the final SSE event for the UI.
- **Tests** ([tests/test_reports.py](../backend/tests/test_reports.py)): an
  autouse stub so report tests are deterministic and make **no** live LLM calls.

Still open: a whole-run wall-clock deadline (#3), the read-only DB role (#4,
needs DBA action), an API auth gate (#5), report call batching (#6), and the
Phase-6 benchmarks + externalized state (#7).
