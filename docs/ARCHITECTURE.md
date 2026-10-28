# Architecture

How the Sales Intelligence Platform is put together and how a request flows
through it. Companion docs: [SCHEMA.md](SCHEMA.md) (raw tables),
[DASHBOARD_SPEC.md](DASHBOARD_SPEC.md) (product spec),
[API.md](API.md) (endpoint reference),
[SPEC_COMPLIANCE.md](SPEC_COMPLIANCE.md) (spec → code status),
[DECISIONS.md](DECISIONS.md) (why each choice).

> **Status:** Phase 0 (schema discovery) and Phase 1 (data layer + dashboard
> API) are built. The frontend, the LangGraph agent, AI insights, reports, and
> the scaling/eval work are later phases — marked _(planned)_ below.

---

## 1. Core principle — the LLM never reads raw rows

Every number on the dashboard comes from **deterministic, parameterized SQL**
against a pre-aggregated reporting layer (`mart.*`). No LLM is involved in Phase
1 at all. When the agent arrives (Phase 3) it will only ever: write SQL, let the
database aggregate, and read back **small aggregated results** (≤ ~200 rows).
This keeps results trustworthy, cheap, and injection-resistant.

---

## 2. Layers

```
                    CockroachDB (defaultdb)
  ┌───────────────────────────────────────────────────────────┐
  │  olist.*   raw source tables (read-only)   — see SCHEMA.md  │
  └───────────────────────────────────────────────────────────┘
                              │  db/views.sql  (rebuilt by
                              │  python -m db.refresh_mart)
                              ▼
  ┌───────────────────────────────────────────────────────────┐
  │  mart.*   reporting layer (pre-aggregated, indexed)         │
  │    order_facts · order_item_facts · daily_sales            │
  └───────────────────────────────────────────────────────────┘
                              │  read-only, parameterized SQL
                              ▼
  backend/                                             (Python 3.11+)
    db/session.py        engine + read_only_session (SET TRANSACTION READ ONLY)
    api/filters.py       global filters → SQL fragments (bound params only)
    services/charts.py   one query function per chart/KPI  ← deterministic SQL
    services/cache.py    TTL cache keyed by hash(sql + params)
    api/dashboard.py     FastAPI routes  (/api/...)
    app/main.py          FastAPI app + CORS
                              │  JSON
                              ▼
    frontend/  React + Vite + TS, Recharts, TanStack Query   (planned, Phase 2)
    agent/     LangGraph agent + guards/sql_validator.py     (planned, Phase 3)
```

Namespace packages (no `__init__.py`); modules resolve via `pythonpath = ["."]`
from `backend/` (see `pyproject.toml`).

---

## 3. The reporting layer (`mart.*`)

Built by [`backend/db/views.sql`](../backend/db/views.sql) as **tables** (not
materialized views — see DECISIONS.md D1) and rebuilt with
`python -m db.refresh_mart`. The build enforces the data-quality rules from
DASHBOARD_SPEC.md §4 (no fan-out, deduped reviews, one payment type per order).

### `mart.order_facts` — one row per order (99,441 rows)
`order_id, purchase_date, purchase_month, customer_unique_id, customer_state,
status, items_gmv, freight, n_items, payment_value, main_payment_type,
max_installments, review_score, delivery_days, estimated_days, delay_days,
is_late, delay_bucket`

Items, payments and reviews are each aggregated to order grain in separate CTEs
**before** joining onto `orders`, so order-level sums never fan out.
Indexes: `purchase_date, purchase_month, customer_state, status, delay_bucket`.

### `mart.order_item_facts` — one row per order item (112,650 rows)
`order_id, purchase_date, purchase_month, customer_state, status, product_id,
category, seller_id, seller_state, price, freight_value`
Indexes: `purchase_date, customer_state, category, status, seller_id, order_id`.

### `mart.daily_sales` — additive rollup (58,019 rows)
Grain: `date × purchase_month × customer_state × category × status`
Measures: `gmv, orders, items, freight`
(`status` added to the grain vs. the spec so the global status filter applies
uniformly — DECISIONS.md D5.)
Indexes: `date, purchase_month, customer_state, category, status`.

**Which table backs which metric** (the additive-vs-distinct rule, DECISIONS.md
D6): additive measures (gmv/items/freight) sum safely from `daily_sales`;
distinct order counts come from `order_facts`/`order_item_facts`. See API.md for
the per-endpoint mapping.

---

## 4. Request lifecycle (a chart endpoint)

```
GET /api/charts/trend?date_from=…&states=SP,RJ&granularity=month
        │
        ├─ filter_params()      parse global filters → Filters dataclass
        │                       (unknown statuses dropped; CSV → list)
        ├─ charts.trend(f, …)   build parameterized SQL + bound params
        │     └─ Filters.where("order_facts") → WHERE clauses + :params
        ├─ query_cache.cached(sql, params, loader)   hash(sql+params) → hit? return
        │     └─ loader(): read_only_session → SET statement_timeout → execute
        └─ JSON  { "data": [ {period, gmv, orders, aov}, … ], "meta": {…} }
```

Key safety properties:
- **Read-only:** every query runs inside `SET TRANSACTION READ ONLY`.
- **Parameterized:** filter values are bound (`:date_from`, `= ANY(:states)`),
  never string-formatted — injection-safe by construction.
- **Bounded:** a per-query `statement_timeout` (default 5000 ms) is set.
- **Cached:** identical (sql, params) are served from an in-process TTL cache.

---

## 5. Configuration & security

- All secrets come from `.env` (git-ignored); only `.env.example` is committed.
  `app/config.py` loads them via `pydantic-settings`.
- `DATABASE_URL` uses `cockroachdb+psycopg://` with `sslmode=verify-full`
  (root cert at `%APPDATA%\postgresql\root.crt`).
- `DATABASE_URL_READONLY` is reserved for a dedicated read-only role for the
  agent's SQL (Phase 3).
- The agent's generated SQL will additionally pass a `sqlglot` validator
  (single statement, SELECT/WITH only, table/column whitelist, enforced LIMIT) —
  Phase 3. Phase 1's deterministic SQL does not need it but already follows the
  same read-only / parameterized / timeout discipline.

---

## 6. Phase status

| Phase | Scope | Status |
|---|---|---|
| 0 | Schema discovery → SCHEMA.md | ✅ done |
| 1 | `mart.*` + dashboard API + tests | ✅ done |
| 2 | React/Vite dashboard UI | ⬜ planned |
| 3 | LangGraph agent + SQL guard + CLI | ⬜ planned |
| 4 | AI insights + chat in the dashboard | ⬜ planned |
| 5 | Report composer (Markdown + PDF) | ⬜ planned |
| 6 | Synthetic 1M rows, benchmarks, evals, README, Docker | ⬜ planned |
