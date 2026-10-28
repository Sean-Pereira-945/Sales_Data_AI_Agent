# Spec compliance — [DASHBOARD_SPEC.md](DASHBOARD_SPEC.md)

Section-by-section status of the implementation against the dashboard spec.
Legend: ✅ done · 🟡 partial/deviates (documented) · ⬜ pending a later phase.

The spec describes the full product (data + UI + AI). As of Phase 1 the **data
layer and the API that backs every KPI, chart and filter are built and tested**;
the visual UI is Phase 2 and AI insights are Phase 4. Every data/metric rule the
spec can verify server-side is enforced and covered by tests.

---

## §2 Source tables — ✅
All 11 `olist.*` tables confirmed against [SCHEMA.md](SCHEMA.md), including
`customer_unique_id` (the spec flagged it to verify — it exists, 96,096 distinct)
and the `product_categories` English names. The unused `brazilian_ecom` DB is
ignored.

## §3 Metric dictionary — ✅ (one defined-but-unsurfaced)
| Metric | Status | Where |
|---|---|---|
| GMV = `SUM(price)` (excl. freight) | ✅ | `order_facts.items_gmv` |
| Freight, Freight % | ✅ | `order_facts.freight`; `revenue_by_state` `freight_pct` |
| Orders = distinct orders | ✅ | `order_facts` `COUNT(*)` |
| AOV = GMV/Orders | ✅ | KPIs, trend, revenue_by_state |
| Payment value (never mixed w/ GMV) | ✅ | stored as `order_facts.payment_value`; **not** combined with GMV anywhere |
| Revenue-eligible default | ✅ | `api/filters.py` `REVENUE_ELIGIBLE_STATUSES` |
| Delivery days, Late %, Delay bucket | ✅ | precomputed in `order_facts` |
| Avg review (dedup to 1/order, latest) | ✅ | `views.sql` `rev` CTE (`ROW_NUMBER`) |
| Active sellers | ✅ | `order_item_facts` distinct `seller_id` |
| **Repeat customer %** | 🟡 | computable from `customer_unique_id` in `order_facts`, but no chart/KPI surfaces it (none in §8). Reserved for the agent. |

## §4 Data-quality rules — ✅ (enforced + tested)
1. **No join fan-out** — ✅ items/payments/reviews aggregated to grain before
   join; `test_no_item_fanout_in_gmv`.
2. **Default range 2017-01-01…2018-08-31** — ✅ defaults in `filters.py`;
   `partial_period` flag set when the range exceeds it (`test_partial_period_flag`).
   UI banner is Phase 2.
3. **No PoP comparison on incomplete periods** — ✅ KPI delta suppressed when the
   prior window starts before the data floor (`test_kpis_*`).
4. **Min 30 orders for best/worst rankings** — ✅ enforced on `top-categories`
   (avg_review) and `late-by-state` (`min_orders`, default 30); tested.
5. **Black Friday (24 Nov 2017) recognised, not treated as anomaly** — ⬜ this is
   an AI-insight behaviour (Phase 4); the data for it is present.

**Sanity checks** (spec §4) — ✅ all in `tests/test_mart_sanity.py`: orders = 99,441;
revenue-eligible GMV ≈ R$13.49M; avg review ≈ 4.09; credit-card ≈ 75.4%.

## §5 Reporting layer (`mart`) — ✅ (two documented additions)
`mart.order_facts`, `mart.order_item_facts`, `mart.daily_sales` built by
`db/views.sql`, all spec columns present, indexed on date/month/state/category/
status/seller. Deviations (DECISIONS.md D5): `daily_sales` grain adds `status`
(so the status filter applies) and both fact tables carry `purchase_month` for
fast monthly rollups. Materialized views → rebuilt tables (D1). Agent whitelist
over `mart.*`/`olist.*` is Phase 3.

## §6 Filters — ✅
Global date / state (multi) / category (multi) / status (default revenue-eligible)
all implemented; `GET /api/filters/meta` returns allowed values + date bounds.
Local per-chart controls implemented (see §8). Local controls are additive and
never override the global filters.

## §7 Layout — ✅ (Phase 2)
Built in `frontend/`: sticky global filter bar → KPI row (6 cards) → 2-column grid
of all 8 charts → bottom actions (`Summarize dashboard` / `Generate report`,
disabled until Phases 4–5) → slide-in side chat panel. Responsive (3/2/1-column
KPI reflow; single-column charts on narrow screens).

## §8 Chart specifications
| # | Chart | Data/API | Local controls | Notes |
|---|---|---|---|---|
| — | KPI cards | ✅ | value + Δ% + period label | all six metrics; on-time % = 1−late% |
| 1 | GMV & Orders trend | ✅ | granularity day/week/month ✅; GMV/Orders/AOV all returned for the toggle ✅ | dual-axis rendering = UI |
| 2 | Top categories | ✅ | top_n 5/10/20 (any 1–50) ✅; metric gmv/orders/aov/avg_review ✅; min-30 on avg_review ✅ | horizontal bar = UI |
| 3 | Revenue by state | 🟡 | metric gmv/orders/aov/freight_pct ✅ | sorted **bar** built (the spec's allowed fallback); choropleth map is a future enhancement |
| 4 | Payment mix over time | ✅ | share/absolute/installments ✅ | share-vs-absolute is a UI render of the same rows |
| 5 | ★ Delivery delay → review | ✅ | state & category via global filters | headline verified in data + tests |
| 6 | Late % by state | ✅ | sort ✅; min_orders ✅ | delivery-days secondary axis = UI |
| 7 | Review distribution | ✅ | distribution/trend ✅; category via global | |
| 8 | Seller concentration (Pareto) | 🟡 | `buckets` (5–100) instead of a "top-% slider" | full Pareto curve returned; the slider is a UI zoom over the same data |

## §9 AI behaviour — ⬜ Phase 4
Insights from aggregated results only, numbers-grounded, cached by
`hash(chart_id+params)`, "Summarize dashboard". (The result cache and the
no-raw-rows data shape are already in place to support it.)

## §10 UX standards — ✅ (Phase 2)
Implemented in the UI: every title carries its metric + unit (e.g. "GMV (R$),
month"); consistent colour per payment type / delay bucket / review score across
charts (`lib/colors.ts`); empty results show "No orders match these filters";
loading uses shimmer skeletons and a refetch keeps the previous data visible
(`keepPreviousData`); the partial-period banner shows when the range leaves
2017-01-01…2018-08-31. BRL formatting throughout; light/dark via CSS variables.

---

## Summary
- **Built & spec-compliant now:** all source/metric/data-quality rules (§2–§6);
  the data + API for every KPI and all 8 charts (§8); and the full dashboard UI —
  layout (§7) and UX standards (§10).
- **Deviations, all documented in DECISIONS.md:** rebuilt tables vs. matviews (D1);
  `daily_sales` grain + `purchase_month` (D5); source-table choices per the
  additive/distinct rule (D6); category semijoin semantics (D7); seller Pareto
  `buckets` vs. slider; revenue-by-state **bar** (spec's allowed fallback) instead
  of a choropleth map.
- **Pending by design:** AI insights, chat & Black-Friday recognition (Phase 4);
  reports (Phase 5); the choropleth map as a visual enhancement.
