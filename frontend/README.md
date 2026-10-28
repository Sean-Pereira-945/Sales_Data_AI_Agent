# Frontend — Sales Intelligence dashboard

React + Vite + TypeScript SPA. Charts with **Recharts**, data with **TanStack
Query**. Implements the dashboard layout and UX standards from
[../docs/DASHBOARD_SPEC.md](../docs/DASHBOARD_SPEC.md) (§7, §10).

## Run

The backend must be running first (see [../docs/README.md](../docs/README.md)),
by default on `http://127.0.0.1:8000`.

```bash
npm install
npm run dev        # http://localhost:5173  (proxies /api → backend)
```

Other scripts: `npm run build` (typecheck + production build), `npm run preview`,
`npm run typecheck`.

## Config

- Dev calls go through the Vite proxy in `vite.config.ts` (`/api` → backend), so
  there's no CORS. Point it elsewhere with `VITE_API_TARGET`.
- For a non-proxied build, set `VITE_API_BASE` to the API origin.

## Structure

```
src/
  api/        client.ts · types.ts · hooks.ts (one Query hook per endpoint)
  state/      filters.tsx  — global filter context
  lib/        format.ts (BRL/%/★) · colors.ts (per-dimension palette)
  components/ GlobalFilterBar · KpiCards · ChartCard (+AI-insight placeholder)
              ChatPanel · PartialPeriodWarning · ui.tsx · charts/*
  pages/      Dashboard.tsx
```

The per-card AI-insight boxes and the side chat panel are placeholders, wired to
the LangGraph agent in Phase 4.
