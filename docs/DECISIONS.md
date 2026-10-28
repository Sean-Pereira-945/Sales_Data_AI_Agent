# Design Decisions

Rationale for non-obvious choices, so each can be defended in the interview.
Newest phase last.

See also: [ARCHITECTURE.md](ARCHITECTURE.md) · [API.md](API.md) ·
[SPEC_COMPLIANCE.md](SPEC_COMPLIANCE.md).

---

## Phase 1 — Data layer & dashboard API

### D1. Reporting layer as rebuilt *tables*, not materialized views
`db/views.sql` builds `mart.order_facts`, `mart.order_item_facts` and
`mart.daily_sales` with `CREATE TABLE AS SELECT`, rebuilt by
`python -m db.refresh_mart`.

- **Why not materialized views:** CockroachDB materialized views do not refresh
  automatically and cannot be incrementally maintained; you still run an explicit
  `REFRESH`. They also can't carry arbitrary secondary indexes as flexibly. For a
  **static historical dataset** (Olist, 2016–2018) the refresh cadence is "once",
  so a plain table is simpler, is as fast to read, and lets us add exactly the
  indexes the dashboard needs.
- **Trade-off:** with live data we'd schedule the refresh (or move to incremental
  rollups). The spec anticipated this ("fall back to tables rebuilt by the script"),
  and the script is the single rebuild entry point.

### D2. No join fan-out — aggregate to grain *before* joining
`mart.order_facts` aggregates items, payments and reviews to **order grain in
separate CTEs**, then `LEFT JOIN`s them onto `orders`. Joining `order_items`
directly to `order_payments` would multiply rows (a 3-item order with 2 payments
→ 6 rows) and inflate every sum.
- Guard: `test_no_item_fanout_in_gmv` asserts order-grain GMV == item-grain GMV.

### D3. Reviews de-duplicated to one per order (latest)
`order_reviews` has ~98.6k distinct orders across 99.2k rows (some orders have
multiple reviews). We keep the latest by `created_date, answered_at` via
`ROW_NUMBER()`. Using a raw join would double-count scores.

### D4. `main_payment_type` = the payment type of the **largest** payment
An order can split across payment types (e.g. voucher + credit card). We attribute
the order to the type with the greatest `payment_value` (tie-broken by
`payment_sequential`). This keeps a clean one-type-per-order dimension for the
payment-mix chart without fan-out.

### D5. `daily_sales` grain includes `status` (deviation from spec)
The spec lists `date × customer_state × category`. We added `status` to the grain
so the **global status filter applies uniformly** to the endpoints that read this
rollup. Grain stays small (58k rows) because the combinations are sparse.

### D6. Additive vs. distinct — which table each metric reads
This is the key correctness rule behind the source-table choices:
- **Additive measures** (`gmv`, `items`, `freight`) can be summed from
  `daily_sales` at any grouping.
- **Distinct order counts are *not* additive** across category: an order with
  items in two categories appears in two `daily_sales` rows, so `SUM(orders)`
  would double-count — *unless* the grouping is **by category** (a fixed category
  maps each order to exactly one row, since an order has one date/state/status).
- Therefore:
  - **Top categories** (grouped by category) → `daily_sales` (additive + correct
    order counts).
  - **Trend, revenue-by-state, KPIs' orders/AOV, payment mix, delivery, late %,
    reviews** → `order_facts` (true order grain; `COUNT(*)` = exact orders,
    `SUM(items_gmv)` additive).
  - **Active sellers, seller Pareto, category avg-review** → `order_item_facts`
    with `COUNT(DISTINCT order_id)` where an order count is needed.

### D7. Category filter on order-grain charts = "order contains the category"
Order-grain tables have no category column. When a category filter is applied to
an order-grain chart we use an `EXISTS` semijoin against `order_item_facts`:
the order qualifies if it contains ≥1 item in a selected category, and its **full**
GMV counts. Item-grain charts (top categories) instead attribute item-level GMV to
each category. Two different, each-correct semantics — documented so the numbers
are explainable.

### D8. Injection-safe by construction
Every filter value is bound as a SQL **parameter** (`:date_from`, `= ANY(:states)`,
…), never string-formatted. Unknown statuses are dropped; unknown states/categories
simply match no rows (`test_filters_apply`). `services/charts.run` also sets
`statement_timeout` per query. (The agent's generated SQL gets the stronger
`sqlglot` guard in Phase 3; this is the deterministic layer.)

### D9. Cache keyed by `hash(sql + params)`
`services/cache.py` is an in-process TTL cache (default 300s) with a
`hash(normalised_sql + params)` key — the same key scheme the agent layer will
reuse. Interface (`get`/`set`/`cached`) is deliberately swappable for Redis later.

### D10. CockroachDB SQL portability notes (learned against the live DB)
- `WIDTH_BUCKET(float, float, float, int)` is **not** accepted; the seller-Pareto
  bucketing uses `FLOOR(pct_rank * n) + 1` arithmetic instead.
- Cockroach rejects mixed-type arithmetic (`<float> * <int>`); operands are cast
  explicitly (`CAST(:buckets AS FLOAT)`).
- `:name::TYPE` collides with SQLAlchemy's `:param` syntax — use `CAST(:name AS TYPE)`.
- `DATE_TRUNC('week'|'month', date)` and `= ANY(:list)` work as in Postgres.

---

## Phase 2 — Dashboard UI

### D11. Global filters in one context; local params per hook
A single `FilterProvider` (React context + reducer) holds the global filters.
Each chart's TanStack Query hook composes the global filters with its own local
params and includes both in the query key, so one filter change invalidates and
refetches every card consistently — no prop-drilling, no manual refresh wiring.

### D12. `keepPreviousData` instead of spinners on refetch
Query hooks use `placeholderData: keepPreviousData`, so changing a filter keeps
the previous chart visible (dimmed with a small "refreshing" dot) rather than
flashing a blank skeleton. First load still shows a shimmer skeleton. This is the
spec's §10 "a refresh keeps the previous data visible".

### D13. Vite dev proxy instead of CORS
`vite.config.ts` proxies `/api` → the FastAPI backend, so the browser makes
same-origin requests in dev and we avoid CORS entirely; the frontend code calls
relative paths. Other environments set `VITE_API_BASE`. (The backend still sends
permissive CORS headers for 5173 as a belt-and-braces fallback.)

### D14. Fixed colour maps per dimension
`lib/colors.ts` pins a colour to each payment type, delay bucket and review score
so they read the same across every chart (spec §10). Arbitrary dimensions
(states, sellers) draw from one shared categorical palette.

### D15. Revenue-by-state as a bar, not a choropleth
The spec allows "a sorted bar as fallback" for the Brazil map. We shipped the bar
(correct, fast, no geo assets) and left the choropleth as a later visual
enhancement — the data endpoint already returns per-state values keyed by the
two-letter state code, so adding a map is purely front-end.

### D16. Recharts + TanStack Query
Recharts (declarative SVG, React-native) for charts and TanStack Query for
server-state (caching, dedup, background refetch) — both named in CLAUDE.md.
Pinned, ≥2-week-old versions. Bundle is ~610 kB (Recharts dominates); acceptable
for an internal dashboard, and code-splittable later if needed.
