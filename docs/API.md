# Dashboard API reference (Phase 1)

Base URL (dev): `http://localhost:8000`  ·  Interactive docs: `/docs`
All endpoints are `GET`, read-only, and return JSON. No authentication yet
(single-tenant screening project). No LLM is involved in any of these routes.

Run the server:
```bash
cd backend
.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
```

---

## Global filters

Every chart and KPI endpoint accepts the same global filters as query params.
Values are always bound as SQL parameters (injection-safe).

| Param | Type | Default | Notes |
|---|---|---|---|
| `date_from` | date (`YYYY-MM-DD`) | `2017-01-01` | inclusive |
| `date_to` | date (`YYYY-MM-DD`) | `2018-08-31` | inclusive |
| `states` | CSV | all | e.g. `SP,RJ`; matches `customer_state` |
| `categories` | CSV | all | English category names |
| `statuses` | CSV | revenue-eligible | default excludes `canceled`, `unavailable`; unknown values ignored |

The default date window and the revenue-eligible status default come from
DASHBOARD_SPEC.md §4. Widening the date range sets a `partial_period` flag in
responses (the UI shows a warning).

**Category filter semantics** differ by grain (DECISIONS.md D7): on order-grain
charts an order matches if it *contains* an item in a selected category (full
order value counts); on item-grain charts item-level value is attributed per
category.

---

## Meta

### `GET /health`
`{ "status": "ok" }`

### `GET /api/filters/meta`
Allowed filter values and data bounds (cached 1h). Use it to populate the UI
filter controls.
```json
{
  "states": ["AC", "AL", ... "SP", "TO"],        // 27
  "categories": ["agro_industry_and_commerce", ... ],  // 73
  "statuses": ["approved","canceled","created","delivered","invoiced","processing","shipped","unavailable"],
  "date_min": "2016-09-04", "date_max": "2018-10-17",
  "default_date_from": "2017-01-01", "default_date_to": "2018-08-31",
  "default_statuses": ["approved","created","delivered","invoiced","processing","shipped"],
  "currency": "BRL"
}
```

---

## KPIs

### `GET /api/kpis`
Six KPI cards for the current filters, each with a delta vs. the prior
equal-length period. Source: `order_facts` (GMV/orders/AOV/review/on-time) +
`order_item_facts` (active sellers).

```json
{
  "cards": [
    {"key":"gmv","label":"GMV","unit":"BRL","value":13449529.68,"prev_value":null,"delta_pct":null},
    {"key":"orders","label":"Orders","unit":null,"value":97910,...},
    {"key":"aov","label":"AOV","unit":"BRL","value":137.37,...},
    {"key":"avg_review","label":"Avg review","unit":"stars","value":4.117,...},
    {"key":"on_time_pct","label":"On-time %","unit":"%","value":93.21,...},
    {"key":"active_sellers","label":"Active sellers","unit":null,"value":...}
  ],
  "comparison_label": "no comparable prior period (before data start)",
  "partial_period": false,
  "currency": "BRL"
}
```
`delta_pct` / `prev_value` are `null` when the prior window predates the dataset
(DECISIONS.md — avoids absurd deltas on the default full-range view). On-time % =
1 − Late %.

---

## Charts

Each returns `{ "data": [...], "meta": {...} }`. `local params` are in addition
to the global filters.

| ID | Endpoint | Local params | Source |
|---|---|---|---|
| 1 | `GET /api/charts/trend` | `granularity` = `day`\|`week`\|`month` (month) | `order_facts` |
| 2 | `GET /api/charts/top-categories` | `top_n` 1–50 (10); `metric` = `gmv`\|`orders`\|`aov`\|`avg_review` | `daily_sales` (+`order_facts` for avg_review) |
| 3 | `GET /api/charts/revenue-by-state` | `metric` = `gmv`\|`orders`\|`aov`\|`freight_pct` | `order_facts` |
| 4 | `GET /api/charts/payment-mix` | `view` = `share`\|`absolute`\|`installments` | `order_facts` |
| 5 | `GET /api/charts/delay-vs-review` | — | `order_facts` |
| 6 | `GET /api/charts/late-by-state` | `min_orders` 0–1000 (30); `sort` = `late_pct`\|`delivery_days`\|`orders` | `order_facts` |
| 7 | `GET /api/charts/review-distribution` | `view` = `distribution`\|`trend` | `order_facts` |
| 8 | `GET /api/charts/seller-concentration` | `buckets` 5–100 (20) | `order_item_facts` |

### 1. Trend — `trend`
Each row has `period, gmv, orders, aov` (the UI toggles which to plot; dual-axis
GMV vs. Orders). `meta.granularity`, `meta.currency`, `meta.partial_period`.
```json
{"data":[{"period":"2017-01-01","gmv":120098.27,"orders":787,"aov":152.60}, ...],
 "meta":{"granularity":"month","currency":"BRL","partial_period":false}}
```

### 2. Top categories — `top_categories`
Rows `{category, value, orders, gmv}` sorted by the chosen `metric`. For
`metric=avg_review`, only categories with ≥ 30 reviewed orders are returned
(DASHBOARD_SPEC.md §4 rule 4), `value` = avg stars.

### 3. Revenue by state — `revenue_by_state`
Rows `{state, value, gmv, orders, aov, freight_pct}`; `value` echoes the chosen
`metric`. Sorted by GMV desc (SP leads).

### 4. Payment mix — `payment_mix`
- `view=share`/`absolute`: rows `{period (month), payment_type, orders, gmv}`.
- `view=installments`: rows `{installments, orders, avg_order_value}`.

### 5. Delay vs. review — `delay_vs_review` ★ (headline)
Always five rows in order `early, on time, 1-3 days late, 4-7 days late,
8+ days late`, each `{delay_bucket, avg_review, orders}`. Delivered orders with a
review only. Demonstrates the headline: avg review falls from ~4.3★ (early) to
~1.7★ (8+ days late).

### 6. Late % by state — `late_by_state`
Rows `{state, late_pct, avg_delivery_days, orders}`, filtered to
`orders ≥ min_orders`, sorted by `sort`.

### 7. Review distribution — `review_distribution`
- `view=distribution`: five rows `{score 1..5, reviews}`.
- `view=trend`: monthly rows `{period, avg_review, one_star_pct, reviews}`.

### 8. Seller concentration — `seller_concentration`
Pareto curve: rows `{seller_pct, cum_gmv_pct, sellers}` (cumulative GMV share by
seller rank). Confirms platform-dependency risk — e.g. top ~20% of sellers ≈
82% of GMV. `meta.total_sellers`.

---

## Caching
Results are cached in-process by `hash(normalized_sql + params)` with a 300s TTL
(`filters/meta` 1h). Identical requests are served from cache; the key scheme is
shared with the future agent layer (`services/cache.py`).
