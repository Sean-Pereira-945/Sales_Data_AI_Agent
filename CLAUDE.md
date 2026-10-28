# Sales Intelligence Platform — Project Guide for Claude Code

## What this project is
An AI-powered sales intelligence dashboard built as an internship screening project.
- A dashboard with charts. Every chart has its own filters and its own AI summary.
- A chat agent that answers questions about the sales data, summarizes on request, and generates reports with graphs.
- The agent is built with **LangGraph**. The reasons for using it must be documented in the README.
- Evaluators judge three things: **understanding of the system, how it scales, and quality of work.**

## Core architecture principle (do not violate)
**The LLM never reads raw rows.** The LLM writes SQL, the database aggregates, and the LLM only sees small aggregated results (at most about 200 rows).
- Chart data and filters come from **deterministic, parameterized SQL with no LLM involved**.
- The LLM is used only for: intent routing, NL→SQL, insights/summaries, report narrative, and chart spec selection.

## Stack
- **DB:** CockroachDB (Postgres wire-compatible), reached through `DATABASE_URL` in `.env`
- **Backend:** Python 3.11+, FastAPI, SQLAlchemy 2.x + `sqlalchemy-cockroachdb` (psycopg v3), Pydantic v2
- **Agent:** LangGraph (StateGraph, conditional edges, checkpointer for chat memory)
- **LLM:** provider-agnostic wrapper. Model name and API key come from `.env`
- **Frontend:** React + Vite + TypeScript, Recharts, TanStack Query
- **Reports:** Markdown → PDF (WeasyPrint or similar), with charts rendered server-side (matplotlib/plotly)
- **Tests:** pytest. Evals in `backend/evals/`

## CockroachDB specifics
- Connection uses `sslmode=verify-full`, so the root cert must exist:
  - Linux/macOS: `~/.postgresql/root.crt`
  - Windows: `%APPDATA%\postgresql\root.crt`
- Default port is 26257. The driver URL scheme for SQLAlchemy is `cockroachdb+psycopg://`.
- Cockroach differs from Postgres in places. Test materialized views, `DATE_TRUNC`, window functions and index syntax against the real DB before relying on them.
- Use transaction retry logic (Cockroach can return serialization error 40001).

## Security rules (non-negotiable)
- **Never hardcode or print credentials.** Read everything from `.env`, which is git-ignored. Commit only `.env.example`.
- The agent's SQL runs through `guards/sql_validator.py`:
  - single statement only
  - `SELECT`/`WITH` only (parse with `sqlglot`, not regex)
  - whitelist of tables and columns
  - `LIMIT` is enforced
  - `statement_timeout` is set
- Prefer a separate **read-only DB role** for agent queries.
- Treat user chat input as untrusted (prompt injection). Never let it alter system prompts or the guard rules.

## Folder structure
```
backend/
  app/main.py            FastAPI entry
  api/                   dashboard.py, chat.py, insights.py, reports.py
  agent/                 state.py, graph.py, nodes/, prompts/
  db/                    session.py, schema_introspect.py, views.sql, seed/
  guards/                sql_validator.py
  services/              cache.py, charts.py, report_builder.py
  evals/                 questions.json, run_evals.py
  tests/
frontend/src/            components/, pages/, api/
docs/                    SCHEMA.md, ARCHITECTURE.md, SCALING.md, DECISIONS.md
scripts/                 generate_synthetic.py, benchmark.py
.env.example
README.md
```

## LangGraph design
State: `question, intent, filters, schema_context, sql, result, error, retries, chart_spec, insight, report_sections, messages`

Nodes:
1. `intent_router` → qa | chart | summary | report
2. `schema_context` → injects only the relevant tables/columns plus a few sample values
3. `sql_generator`
4. `sql_validator` → if rejected, go back to the generator with the reason
5. `executor` → if there is a DB error, go back to the generator (max 3 retries, then fail gracefully)
6. `analyzer` → computes deltas, top-N, anomalies in Python from the aggregated result
7. `chart_spec` (when intent is chart) → validated JSON (type, x, y, series)
8. `insight_writer` → a short, numbers-grounded summary
9. `report_composer` (when intent is report) → loops over sections and reuses steps 3–8

Checkpointer: conversation memory keyed by `thread_id` for follow-ups ("now only for West").

## Scaling checklist
- Indexes on date, region, product, and category columns
- Pre-aggregated views or rollup tables (daily/monthly × region × category)
- Cache keyed by `hash(sql + params)`, with a TTL
- Async endpoints and a connection pool
- `scripts/benchmark.py` measures latency at the existing size and at ~1M rows. Record the numbers in `docs/SCALING.md`

## Working rules for Claude Code
- Work **phase by phase** (see PROMPTS.md). Stop at the end of each phase with a summary of what was built, how to run it, and what is next.
- Explain non-obvious design decisions in `docs/DECISIONS.md`. The developer must be able to defend every choice in the interview.
- Write tests alongside code. Run them before declaring a phase done.
- Keep functions small and typed. No dead code, no unused deps.
- Commit after each phase with a clear message.
