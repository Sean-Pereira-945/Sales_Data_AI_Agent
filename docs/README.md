# Docs index

Documentation for the Sales Intelligence Platform. Start here.

| Doc | What it covers |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System layers, the reporting layer (`mart.*`), request lifecycle, security, and phase status |
| [API.md](API.md) | Dashboard API reference — every endpoint, params, and response shapes |
| [DASHBOARD_SPEC.md](DASHBOARD_SPEC.md) | The product spec (source of truth for metrics, charts, filters) |
| [SPEC_COMPLIANCE.md](SPEC_COMPLIANCE.md) | Section-by-section build status against the spec, with deviations |
| [DECISIONS.md](DECISIONS.md) | Why each non-obvious choice was made (defensible in interview) |
| [SCHEMA.md](SCHEMA.md) | Phase 0 read-only introspection of the raw `olist.*` tables |

## What's built so far

- **Phase 0 — Schema discovery:** read-only introspection of the Olist dataset
  → [SCHEMA.md](SCHEMA.md).
- **Phase 1 — Data layer + dashboard API (no AI):** the `mart.*` reporting layer
  (`db/views.sql`, rebuilt by `python -m db.refresh_mart`) and a FastAPI dashboard
  API serving 6 KPIs + 8 charts from deterministic, parameterized, read-only SQL.
  23 passing tests (spec sanity checks + every endpoint).
- **Phase 2 — Dashboard UI:** React + Vite + TypeScript SPA (Recharts + TanStack
  Query) — global filter bar, KPI row, a 2-column grid of all 8 charts with their
  own local controls, partial-period warning, per-card AI-insight placeholders,
  and a side chat-panel placeholder. See [ARCHITECTURE.md §4a](ARCHITECTURE.md#4a-frontend-phase-2).
- **Phase 3 — LangGraph agent:** NL→SQL→insight agent (router → schema →
  generator → `sqlglot` guard → executor with retry → analyzer → chart-spec →
  insight), Gemini LLM integration with an offline stub, and a CLI
  (`python -m agent.cli`). The SQL guard enforces single-statement, read-only,
  table/column-whitelist, LIMIT. See [ARCHITECTURE.md §4b](ARCHITECTURE.md#4b-the-agent-phase-3).

- **Phase 4 — AI in the dashboard:** per-chart + KPI AI insights (cached,
  generated on demand), a "Summarize dashboard" brief, and a streaming chat panel
  with conversation memory and inline charts — all via `api/insights.py` and
  `api/chat.py`. See [ARCHITECTURE.md §4c](ARCHITECTURE.md#4c-ai-in-the-dashboard-phase-4).

- **Phase 5 — Reports:** a `report_composer` that plans sections dynamically from
  the request (a per-request mix of reliable built-in charts and LLM-written
  custom charts, with a deterministic keyword fallback), runs the guarded queries,
  renders charts server-side (matplotlib), writes the narrative, and exports
  **Markdown + PDF** — `POST /api/reports` + download
  endpoints, and a "Generate report" dialog in the UI. See
  [ARCHITECTURE.md §4d](ARCHITECTURE.md#4d-reports-phase-5).

Phase 6 adds a latency benchmark (→ [SCALING.md](SCALING.md)), a 20-question eval
harness, the root README, and Docker/compose. Benchmarking at a synthetic ~1M-row
scale is left as future work; see [ARCHITECTURE.md §6](ARCHITECTURE.md#6-phase-status).

## Run it

**Backend** (needs `.env` with `DATABASE_URL`; see `../.env.example`):
```bash
cd backend
.venv/Scripts/python.exe -m db.refresh_mart                       # (re)build mart.*
.venv/Scripts/python.exe -m pytest -q                             # 23 tests
.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
# → http://localhost:8000/docs
```

**Frontend** (in a second terminal, with the backend running):
```bash
cd frontend
npm install
npm run dev
# → http://localhost:5173   (Vite proxies /api to the backend on :8000)
```

**Agent CLI** (works offline with the stub; set `LLM_PROVIDER=gemini`,
`LLM_API_KEY`, and `LLM_MODEL=gemini-2.5-flash` in `.env` for Gemini-powered
NL→SQL):
```bash
cd backend
.venv/Scripts/python.exe -m agent.cli "top 5 categories by revenue"
.venv/Scripts/python.exe -m agent.cli          # interactive REPL (keeps memory)
```
