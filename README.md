# Sales Intelligence Platform

An AI-powered sales-intelligence dashboard and chat agent over the
[Olist Brazilian e-commerce dataset](https://www.kaggle.com/olistbr/brazilian-ecommerce).
It pairs a filterable analytics dashboard (charts + KPIs, each with an on-demand
AI insight) with a **LangGraph** agent that answers natural-language questions,
summarizes the dashboard, and composes multi-section PDF/Markdown reports.

**The one rule everything is built around: the LLM never reads raw rows.** The
model only ever writes SQL; CockroachDB does the aggregation; the model sees back
at most ~200 aggregated rows. That keeps answers trustworthy, cheap, and
injection-resistant.

---

## Features

- **Dashboard** — GMV/orders trend, top categories, revenue & AOV by state,
  delivery delay vs. review, late-% by state, review distribution, payment mix,
  seller concentration. Global filters (date / state / category / status); every
  chart has its own AI insight generated on demand.
- **Chat agent** — NL → validated SQL → aggregated result → numbers-grounded
  answer, streamed over SSE with a per-node status trace and follow-up memory.
- **Reports** — a request-driven planner mixes reliable built-in charts with
  LLM-written custom charts, renders them server-side, and exports a
  self-contained **Markdown + PDF**.
- **Deterministic offline mode** — with no LLM key the whole system still runs on
  a built-in stub, so the dashboard, CLI, and tests work without a provider.

---

## Architecture at a glance

```
CockroachDB  olist.*  (raw, read-only)
      │  db/views.sql  (python -m db.refresh_mart)
      ▼
CockroachDB  mart.*   (pre-aggregated, indexed: order_facts · order_item_facts · daily_sales)
      │  read-only, parameterized SQL (never string-formatted)
      ▼
FastAPI backend ── services/charts.py (deterministic SQL) ── api/* (dashboard, insights, chat, reports)
      │                         guards/sql_validator.py  (sqlglot guard = security boundary)
      │                         agent/ (LangGraph: router → schema → sql → validate → execute → analyze → chart → insight)
      ▼  JSON / SSE
React + Vite + TS frontend (Recharts, TanStack Query)
```

Full write-up: **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**. Design rationale:
[docs/DECISIONS.md](docs/DECISIONS.md). A critical review of standards, security,
performance and agent loop-control (with a fix plan):
[docs/ARCHITECTURE_REVIEW.md](docs/ARCHITECTURE_REVIEW.md).

### Why LangGraph

The agent's control flow is a **graph, not a straight line**: the
validator→generator and executor→generator **retry loops** (bounded at 3 attempts,
then a graceful `fail`) are conditional edges — LangGraph's natural primitive. Its
checkpointer gives **per-conversation memory** (`thread_id`) for follow-ups ("now
only for SP") with no session store to build, and it keeps the **LLM and
deterministic steps as separate, unit-testable nodes**. A plain function pipeline
would rebuild branch/retry/checkpoint by hand; a free-form ReAct agent would let
the model pick tools, which fights the "only validated SQL runs" guarantee. See
[ARCHITECTURE.md §4b](docs/ARCHITECTURE.md).

---

## Quick start

### Option A — Docker (one command)

```bash
# 1. Put your config in .env (see .env.example) — DATABASE_URL, LLM_* etc.
# 2. Make the CockroachDB CA cert available (verify-full needs it):
#    Windows: copy %APPDATA%\postgresql\root.crt  → ./certs/root.crt
#    macOS/Linux: cp ~/.postgresql/root.crt         → ./certs/root.crt
docker compose up --build
```
Dashboard → http://localhost:8080  ·  API → http://localhost:8000 (`/docs`).

### Option B — local dev

**Backend** (Python 3.11+):
```bash
cd backend
python -m venv .venv && . .venv/Scripts/activate      # Windows; use .venv/bin/activate on macOS/Linux
pip install ".[dev]"
uvicorn app.main:app --reload --port 8000             # needs mart.* built (python -m db.refresh_mart)
```
**Frontend** (Node 20+):
```bash
cd frontend
npm install
npm run dev                                           # http://localhost:5173 (proxies /api to :8000)
```
**CLI** (no server needed):
```bash
cd backend && python -m agent.cli "top 5 categories by revenue"
```

---

## Configuration

All config is read from `.env` (git-ignored; only `.env.example` is committed).

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | `cockroachdb+psycopg://…?sslmode=verify-full` connection string |
| `DATABASE_URL_READONLY` | *(recommended)* dedicated read-only role for agent SQL |
| `LLM_PROVIDER` / `LLM_MODEL` / `LLM_API_KEY` | provider-agnostic LLM wrapper; empty key → offline stub |
| `SQL_STATEMENT_TIMEOUT_MS` | per-query timeout (default 5000) |
| `SQL_MAX_LIMIT` | hard cap on any agent query's `LIMIT` (default 200) |

> **Note on the LLM key:** this project uses Gemini. The free tier has a low
> daily request quota; a `429 RESOURCE_EXHAUSTED` means the quota is spent, not
> that the key is bad. The app trips a circuit breaker and serves the
> deterministic stub until it recovers. Use `LLM_MODEL=gemini-flash-lite-latest`
> or enable billing for headroom.

---

## Scaling results

Measured with `python -m scripts.benchmark --write` against the real `mart`
reporting layer (99,441 orders). Cold = executed on CockroachDB; warm = TTL-cache
hit. Full detail + methodology in **[docs/SCALING.md](docs/SCALING.md)**.

| query | cold | warm (cache) |
|---|--:|--:|
| `kpis` | 226 ms | ~0 ms |
| `trend_month` | 229 ms | ~0 ms |
| `top_categories` | 125 ms | ~0 ms |
| `revenue_by_state` | 245 ms | ~0 ms |
| `late_by_state` | 246 ms | ~0 ms |

Every dashboard query hits a **pre-aggregated, indexed `mart.*` table**, so cost
grows with the number of *groups* (months, states, categories), not raw orders —
and the rollup table (`mart.daily_sales`) doesn't grow with order volume at all.
The TTL cache flattens repeat load to ~0 ms. The benchmark accepts multiple
schemas (`--schemas a,b`) to compare sizes; measuring at a true ~1M-order scale is
future work (see [ARCHITECTURE_REVIEW.md §3](docs/ARCHITECTURE_REVIEW.md)). First
thing to fix at that scale: the per-process cache and in-memory report store
should move behind Redis/object storage.

---

## Evaluations

20 questions with ground-truth SQL in [`backend/evals/questions.json`](backend/evals/questions.json);
the harness runs each through the **real agent** and compares the *result set*
(execution-based, order/alias-insensitive) to the ground truth:

```bash
cd backend && python -m evals.run_evals --verbose
```

The score is only meaningful with a working LLM key — on the offline stub it
scores the fallback (~35%), not the agent, and the run prints which LLM it used.
`test_evals.py` also asserts all 20 ground-truth queries pass the SQL guard.

---

## Security measures

- **Secrets** come only from `.env` (git-ignored); nothing is hardcoded or logged.
- **The agent's SQL passes a `sqlglot` guard** ([guards/sql_validator.py](backend/guards/sql_validator.py))
  before it can run: single statement, `SELECT`/`WITH` only, table **and** column
  whitelist, cross-database refs blocked, comments stripped, `LIMIT` enforced. The
  canonical re-serialized SQL is what executes.
- **Execution is read-only + bounded:** every query runs in a `READ ONLY`
  transaction with a `statement_timeout`.
- **Untrusted chat input** can't alter the system prompts or the guard, and is
  length-capped at the API edge.
- **Known gap (documented, not hidden):** queries currently run over the main
  `DATABASE_URL` connection; a dedicated least-privilege read-only DB role is the
  recommended outer boundary — see [ARCHITECTURE_REVIEW.md §2](docs/ARCHITECTURE_REVIEW.md).

---

## Testing

```bash
cd backend && pytest -q          # 70 tests: guard, dashboard, agent graph, AI API, reports, evals
```
Report/agent tests run on the deterministic stub, so CI makes **no** live LLM
calls. Frontend: `cd frontend && npm run typecheck`.

---

## Limitations & future work

- **Operational envelope is dev-grade:** no API auth, in-process cache + report
  store (single-worker), no distributed tracing/metrics. The scaling path and a
  prioritized fix backlog are in [ARCHITECTURE_REVIEW.md §5](docs/ARCHITECTURE_REVIEW.md).
- **Least-privilege DB role** (`DATABASE_URL_READONLY`) is wired in config but not
  yet provisioned — the top security item.
- **Agent hang safety:** per-call LLM timeout, 429 circuit breaker, and an explicit
  graph recursion limit are in place; a whole-run wall-clock deadline is still TODO.
- **Report cost:** a report fires many LLM calls; batching/caching narratives is
  the biggest latency+quota win left.
- **Data is static** (Olist is a historical dump), and the benchmark currently
  measures the real ~100k-order dataset; exercising a true ~1M-order load is
  future work.

---

## Repository layout

```
backend/   FastAPI app · agent/ (LangGraph) · services/ · guards/ · db/ · evals/ · tests/
frontend/  React + Vite + TS dashboard (components/, pages/, api/)
scripts/   benchmark.py
docs/      ARCHITECTURE · ARCHITECTURE_REVIEW · DECISIONS · SCALING · SCHEMA · API · DASHBOARD_SPEC · SPEC_COMPLIANCE
```
