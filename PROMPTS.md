# Phase prompts — paste one at a time into Claude Code

Before Phase 0, do these steps yourself:
1. `mkdir sales-intel && cd sales-intel && git init`
2. Put `CLAUDE.md` and this file in the repo root.
3. Download the Cockroach root cert using the command from the Cockroach console.
4. Create `.env` (never commit it):
   ```
   DATABASE_URL=cockroachdb+psycopg://USER:PASSWORD@HOST:26257/defaultdb?sslmode=verify-full
   LLM_PROVIDER=anthropic
   LLM_MODEL=
   LLM_API_KEY=
   ```
5. Start `claude` in the repo.

---

## Phase 0 — Discover the data
```
Read CLAUDE.md. Set up the Python backend skeleton (pyproject, .gitignore incl. .env, .env.example).
Write db/session.py and db/schema_introspect.py, then connect to the database read-only and:
- list all tables, columns, types, row counts, and indexes
- sample 5 rows per table
- find date ranges and the distinct values of low-cardinality columns
Write the findings to docs/SCHEMA.md, including which columns are dimensions vs measures.
Do NOT modify any data. If the DB has no sales data, stop and tell me.
Propose a list of 6 dashboard charts suited to this data and wait for my approval.
```

## Phase 1 — Data layer and dashboard API (no AI)
```
Using the approved charts, build:
- db/views.sql: indexes + rollup views/tables (test Cockroach compatibility)
- api/dashboard.py: one endpoint per chart, parameterized SQL, filters (date range, region, category, product etc. based on SCHEMA.md)
- a filters-metadata endpoint returning the allowed filter values
- services/cache.py
- pytest tests for every endpoint
Explain the indexing/rollup choices in docs/DECISIONS.md.
```

## Phase 2 — Frontend dashboard
```
Build the React + Vite + TS frontend: a grid of chart cards. Each card has its own filter controls and a placeholder "AI insight" box.
Add a global filter bar and a side chat panel (placeholder for now). Keep it clean and responsive.
```

## Phase 3 — LangGraph agent core
```
Implement agent/state.py, agent/graph.py and the nodes as described in CLAUDE.md
(router → schema_context → sql_generator → sql_validator → executor with retry loop → analyzer → insight_writer).
Implement guards/sql_validator.py with sqlglot and add tests for injection attempts
(DROP, multiple statements, comments, non-whitelisted tables, UNION into system tables).
Add a CLI (python -m agent.cli) so I can test questions before wiring the UI.
Write docs/ARCHITECTURE.md with a mermaid diagram of the graph and a "Why LangGraph" section.
```

## Phase 4 — AI features in the dashboard
```
- api/insights.py: per-chart AI summary for the current filters (computed from aggregated data, cached)
- api/chat.py: streaming chat with thread_id memory via the LangGraph checkpointer; responses can include chart specs rendered inline
- "Summarize dashboard" button
Wire everything to the frontend.
```

## Phase 5 — Reports
```
Add the report_composer node and api/reports.py: the user asks for a report (e.g. "Q3 regional performance"),
the agent plans sections, runs queries, renders charts, writes the narrative, and exports Markdown + PDF.
Add a "Generate report" UI with a download.
```

## Phase 6 — Scale, evals, polish
```
- scripts/generate_synthetic.py: ~1M rows into a SEPARATE table/schema matching the real one
- scripts/benchmark.py: dashboard + agent latency at both sizes, with and without cache → docs/SCALING.md
- evals/questions.json: 20 questions with ground-truth SQL; run_evals.py reports accuracy
- README: setup, architecture diagram, why LangGraph, scaling results, eval score, security measures, limitations and future work
- Dockerfile + docker-compose for one-command run
```

---

## After every phase, ask Claude Code
```
Explain what you built in this phase as if I'm being interviewed on it: the data flow, the key decisions, the alternatives you rejected, and how it behaves at 100x the data.
```
