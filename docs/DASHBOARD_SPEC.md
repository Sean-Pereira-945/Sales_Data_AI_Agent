# Dashboard Specification — Olist Sales Intelligence

Source: CockroachDB, database `defaultdb`, schema `olist` (NOT `public`). Ignore the unused `brazilian_ecom` database.
Currency: BRL (R$). Label it on every monetary figure.

---

## 1. Purpose and story order
The dashboard answers four questions, in this order:
1. **Overview:** How is the business doing, and is it growing?
2. **Sales & Products:** What sells, and how do customers pay?
3. **Customers & Geography:** Where are customers and revenue, and what does it cost to serve them?
4. **Operations & Experience:** Are we delivering on time, and does that affect satisfaction?

Headline insight to surface: **late delivery is the strongest driver of low review scores.**

---

## 2. Source tables
| Table | Grain | Key columns |
|---|---|---|
| `olist.orders` | order (~99k) | order_id, customer_id, status, purchased_at, delivered_customer_date, estimated_delivery_date |
| `olist.customers` | customer per order | customer_id, customer_unique_id (verify it exists), state, city |
| `olist.order_items` | order item (~113k) | order_id, product_id, seller_id, price, freight_value |
| `olist.products` → `olist.product_categories` | product | product_id, category (English name) |
| `olist.sellers` | seller | seller_id, state |
| `olist.order_payments` | payment (many per order) | order_id, payment_type, payment_value, installments |
| `olist.reviews` via `olist.order_reviews` | review | score (1–5), created_date |
| geolocation tables | state/zip | lat, long (for the map) |

Column names above are indicative. Confirm them against `docs/SCHEMA.md` and adjust.

---

## 3. Metric dictionary (single source of truth)
| Metric | Definition | Notes |
|---|---|---|
| GMV | `SUM(order_items.price)` | Excludes freight |
| Freight | `SUM(order_items.freight_value)` | Reported separately |
| Freight % | Freight ÷ GMV | |
| Orders | `COUNT(DISTINCT order_id)` | |
| AOV | GMV ÷ Orders | |
| Payment value | `SUM(order_payments.payment_value)` | Includes freight and vouchers. **Never combine with GMV.** |
| Revenue-eligible orders | status NOT IN ('canceled','unavailable') | Default status filter |
| Delivery days | delivered_customer_date − purchased_at | Delivered orders only |
| Late % | delivered orders with delivered date > estimated date ÷ delivered orders | |
| Delay bucket | early / on time / 1–3 days late / 4–7 days late / 8+ days late | Based on delivered − estimated |
| Avg review score | mean(score) after deduplicating to **one review per order** (latest) | |
| Repeat customer % | `customer_unique_id` with >1 order ÷ all `customer_unique_id` | Never use `customer_id` (unique per order) |
| Active sellers | distinct seller_id with ≥1 item in the period | |

---

## 4. Data quality rules (must be enforced)
1. **No join fan-out.** Aggregate items, payments and reviews to order grain *before* joining. Never join `order_items` directly to `order_payments`.
2. **Default date range: 2017-01-01 to 2018-08-31.** Sep–Dec 2016 is sparse, and Sep–Oct 2018 is truncated and mostly cancellations. Users may widen it, but the UI shows a "partial period" warning.
3. **No period-over-period comparison on incomplete months.**
4. **Minimum volume of 30 orders** for any best/worst ranking (categories, states, sellers).
5. **Known event:** Black Friday, 24 Nov 2017. AI insights should identify it, not treat it as an anomaly to ignore.

### Sanity checks (add as pytest tests against the mart)
- Total orders ≈ 99k
- Total GMV ≈ R$13–14M
- Avg review ≈ 4.0–4.1
- Credit card ≈ 70–80% of payments

A large deviation indicates a fan-out or filter bug.

---

## 5. Reporting layer (schema `mart`)
Built by `db/views.sql` plus a refresh script. Test Cockroach materialized-view support, and fall back to tables rebuilt by the script.

**`mart.order_facts`**: one row per order
`order_id, purchase_date, purchase_month, customer_unique_id, customer_state, status, items_gmv, freight, n_items, payment_value, main_payment_type, max_installments, review_score, delivery_days, estimated_days, delay_days, is_late, delay_bucket`

**`mart.order_item_facts`**: one row per order item
`order_id, purchase_date, customer_state, status, product_id, category, seller_id, seller_state, price, freight_value`

**`mart.daily_sales`**: date × customer_state × category
`date, customer_state, category, gmv, orders, items, freight`

Indexes: date/month, customer_state, category, status, seller_id.

All dashboard queries and agent-generated SQL target `mart.*` by default. The agent's SQL whitelist covers `mart.*` and, read-only, `olist.*`.

---

## 6. Filters
**Global** (apply to every chart): date range, customer state (multi-select), category (multi-select), order status (default = revenue-eligible).
Endpoint `GET /api/filters/meta` returns the allowed values and the min/max date.

**Local:** per-chart controls, listed in section 8. Local controls never override global filters.

---

## 7. Layout
```
┌──────────── Global filters: Date | State | Category | Status ────────────┐
│ [GMV] [Orders] [AOV] [Avg Review] [On-time %] [Active Sellers]            │
├─────────────────────────────────┬─────────────────────────────────────────┤
│ 1. GMV & Orders trend           │ 2. Top categories                       │
├─────────────────────────────────┼─────────────────────────────────────────┤
│ 3. Revenue by state (map/bar)   │ 4. Payment mix over time                │
├─────────────────────────────────┼─────────────────────────────────────────┤
│ 5. Delivery delay → Review ★    │ 6. Late % by state                      │
├─────────────────────────────────┼─────────────────────────────────────────┤
│ 7. Review score distribution    │ 8. Seller concentration (Pareto)        │
└─────────────────────────────────┴─────────────────────────────────────────┘
                                                   [ AI chat panel → ]
[Summarize dashboard]  [Generate report]
```

---

## 8. Chart specifications
Each chart has its own endpoint `GET /api/charts/<id>` accepting the global filters plus its local params. Each also has an AI insight via `GET /api/insights/<id>` using the same params; results are cached.

### KPI cards
- **Metrics:** GMV, Orders, AOV, Avg review, On-time % (= 1 − Late %), Active sellers
- **Each card shows:** value, Δ% vs the prior equal-length period, and the comparison period label
- **AI insight:** which KPI moved most, and the likely driver

### 1. GMV & Orders trend
- **Chart:** line, dual axis (GMV in R$ on the left, Orders on the right)
- **Local controls:** granularity (day / week / month, default month), metric toggle (GMV / Orders / AOV)
- **Source:** `mart.daily_sales`
- **AI insight:** growth rate over the period, peaks (Black Friday), seasonality, partial-period caveat

### 2. Top categories
- **Chart:** horizontal bar
- **Local controls:** Top N (5 / 10 / 20, default 10), metric (GMV / Orders / AOV / Avg review)
- **Rule:** min 30 orders for the Avg review metric
- **Source:** `mart.order_item_facts` (+ `order_facts` for reviews)
- **AI insight:** concentration ("Top 5 categories = X% of GMV"), fastest-growing category

### 3. Revenue by state
- **Chart:** choropleth of Brazil (state centroids from geolocation), with a sorted bar as fallback
- **Local controls:** metric (GMV / Orders / AOV / Freight %)
- **Source:** `mart.daily_sales`, `mart.order_item_facts`
- **AI insight:** SP dominance, states where freight % is high (cost-to-serve)

### 4. Payment mix over time
- **Chart:** stacked bar by month
- **Local controls:** absolute vs % share; installments view (distribution of installments vs AOV)
- **Source:** `mart.order_facts` (main_payment_type, max_installments)
- **AI insight:** credit card dominance, boleto trend, link between installments and order value

### 5. ★ Delivery delay → Review score (headline)
- **Chart:** bar of avg review score by delay bucket, with order count shown per bar
- **Local controls:** state, category (in addition to global filters)
- **Filter:** delivered orders with a review only
- **Source:** `mart.order_facts`
- **AI insight:** "Orders 8+ days late average X★ vs Y★ on time", plus the share of 1★ reviews that are late orders

### 6. Late % by state
- **Chart:** bar of Late % with avg delivery days as a marker/secondary axis
- **Local controls:** sort (Late % / delivery days / orders), min orders (default 30)
- **Source:** `mart.order_facts`
- **AI insight:** worst regions for logistics and how they relate to review scores

### 7. Review score distribution
- **Chart:** bar of the count of 1–5★; toggle to a monthly trend of avg score and 1★ share
- **Local controls:** category, view toggle
- **Source:** `mart.order_facts`
- **AI insight:** 1★ share and its trend, worst categories (min 30 orders)

### 8. Seller concentration
- **Chart:** Pareto line of cumulative GMV share by seller rank (percentile)
- **Local controls:** top % slider (default 10%)
- **Source:** `mart.order_item_facts`
- **AI insight:** "Top 10% of sellers generate X% of GMV", framed as platform dependency risk

---

## 9. AI behaviour
- Insights are generated **only from aggregated query results** returned by the chart endpoint. The LLM never sees raw rows.
- Every number in an insight must appear in the provided data. No invented figures.
- Format: 2–3 sentences of the form *what happened → why it likely happened → what to watch*.
- **Summarize dashboard:** reads the KPIs and all chart insights under the current filters. Output order: headline, 3 drivers, 1 risk, 1 recommendation.
- Insights are cached by `hash(chart_id + params)`.

---

## 10. UX standards
- Every title includes its metric and unit, e.g. "GMV (R$), monthly".
- Consistent colour per state, category and payment type across charts.
- Empty results show "No orders match these filters", never a blank chart.
- Loading states use skeletons, and a refresh keeps the previous data visible.
- Show the partial-period warning when the date range includes data before 2017 or after Aug 2018.
