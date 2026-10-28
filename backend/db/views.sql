-- ============================================================================
-- Reporting layer (schema `mart`) for the Sales Intelligence dashboard.
--
-- Built as *tables* (CREATE TABLE AS SELECT), not materialized views. See
-- docs/DECISIONS.md for why: CockroachDB materialized views do not auto-refresh
-- and the Olist dataset is static, so a script-rebuilt table is simpler, faster
-- to query, and lets us add secondary indexes freely.
--
-- Rebuild with:  python -m db.refresh_mart
--
-- Data-quality rules enforced here (see DASHBOARD_SPEC.md §4):
--   * No join fan-out: items, payments and reviews are each aggregated to order
--     grain BEFORE joining onto orders.
--   * Reviews are de-duplicated to one row per order (latest).
--   * main_payment_type is the payment_type of the largest payment on the order.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS mart;

-- ----------------------------------------------------------------------------
-- mart.order_facts — one row per order
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS mart.order_facts;

CREATE TABLE mart.order_facts AS
WITH items AS (
    SELECT order_id,
           SUM(price)          AS items_gmv,
           SUM(freight_value)  AS freight,
           COUNT(*)            AS n_items
    FROM olist.order_items
    GROUP BY order_id
),
pay AS (
    SELECT order_id,
           SUM(payment_value)  AS payment_value,
           MAX(installments)   AS max_installments
    FROM olist.order_payments
    GROUP BY order_id
),
pay_main AS (
    SELECT order_id, payment_type
    FROM (
        SELECT order_id, payment_type,
               ROW_NUMBER() OVER (
                   PARTITION BY order_id
                   ORDER BY payment_value DESC, payment_sequential ASC
               ) AS rn
        FROM olist.order_payments
    ) t
    WHERE rn = 1
),
rev AS (
    SELECT order_id, score
    FROM (
        SELECT orv.order_id, r.score,
               ROW_NUMBER() OVER (
                   PARTITION BY orv.order_id
                   ORDER BY r.created_date DESC, r.answered_at DESC
               ) AS rn
        FROM olist.order_reviews orv
        JOIN olist.reviews r ON r.review_id = orv.review_id
    ) t
    WHERE rn = 1
)
SELECT
    o.order_id,
    o.purchased_at::DATE                                        AS purchase_date,
    DATE_TRUNC('month', o.purchased_at)::DATE                   AS purchase_month,
    c.customer_unique_id,
    c.state                                                     AS customer_state,
    o.order_status                                              AS status,
    i.items_gmv,
    i.freight,
    COALESCE(i.n_items, 0)                                      AS n_items,
    p.payment_value,
    pm.payment_type                                             AS main_payment_type,
    p.max_installments,
    rv.score                                                    AS review_score,
    (o.delivered_customer_at::DATE - o.purchased_at::DATE)      AS delivery_days,
    (o.estimated_delivery_date - o.purchased_at::DATE)          AS estimated_days,
    (o.delivered_customer_at::DATE - o.estimated_delivery_date) AS delay_days,
    CASE
        WHEN o.delivered_customer_at IS NULL THEN NULL
        ELSE (o.delivered_customer_at::DATE > o.estimated_delivery_date)
    END                                                         AS is_late,
    CASE
        WHEN o.delivered_customer_at IS NULL THEN NULL
        WHEN (o.delivered_customer_at::DATE - o.estimated_delivery_date) < 0  THEN 'early'
        WHEN (o.delivered_customer_at::DATE - o.estimated_delivery_date) = 0  THEN 'on time'
        WHEN (o.delivered_customer_at::DATE - o.estimated_delivery_date) <= 3 THEN '1-3 days late'
        WHEN (o.delivered_customer_at::DATE - o.estimated_delivery_date) <= 7 THEN '4-7 days late'
        ELSE '8+ days late'
    END                                                         AS delay_bucket
FROM olist.orders o
JOIN olist.customers c   ON c.customer_id = o.customer_id
LEFT JOIN items i        ON i.order_id = o.order_id
LEFT JOIN pay p          ON p.order_id = o.order_id
LEFT JOIN pay_main pm    ON pm.order_id = o.order_id
LEFT JOIN rev rv         ON rv.order_id = o.order_id;

CREATE INDEX of_purchase_date_idx ON mart.order_facts (purchase_date);
CREATE INDEX of_purchase_month_idx ON mart.order_facts (purchase_month);
CREATE INDEX of_state_idx          ON mart.order_facts (customer_state);
CREATE INDEX of_status_idx         ON mart.order_facts (status);
CREATE INDEX of_delay_bucket_idx   ON mart.order_facts (delay_bucket);

-- ----------------------------------------------------------------------------
-- mart.order_item_facts — one row per order item
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS mart.order_item_facts;

CREATE TABLE mart.order_item_facts AS
SELECT
    oi.order_id,
    o.purchased_at::DATE                        AS purchase_date,
    DATE_TRUNC('month', o.purchased_at)::DATE   AS purchase_month,
    c.state                                     AS customer_state,
    o.order_status                              AS status,
    oi.product_id,
    COALESCE(pc.category_name_en, 'unknown')    AS category,
    oi.seller_id,
    s.state                                     AS seller_state,
    oi.price,
    oi.freight_value
FROM olist.order_items oi
JOIN olist.orders o            ON o.order_id = oi.order_id
JOIN olist.customers c         ON c.customer_id = o.customer_id
LEFT JOIN olist.products p     ON p.product_id = oi.product_id
LEFT JOIN olist.product_categories pc ON pc.category_id = p.category_id
LEFT JOIN olist.sellers s      ON s.seller_id = oi.seller_id;

CREATE INDEX oif_purchase_date_idx  ON mart.order_item_facts (purchase_date);
CREATE INDEX oif_state_idx          ON mart.order_item_facts (customer_state);
CREATE INDEX oif_category_idx       ON mart.order_item_facts (category);
CREATE INDEX oif_status_idx         ON mart.order_item_facts (status);
CREATE INDEX oif_seller_idx         ON mart.order_item_facts (seller_id);
CREATE INDEX oif_order_idx          ON mart.order_item_facts (order_id);

-- ----------------------------------------------------------------------------
-- mart.daily_sales — date x customer_state x category x status rollup
--
-- NOTE: status is included in the grain (a deliberate deviation from the spec's
-- "date x state x category") so the global status filter applies uniformly to
-- the trend / top-categories / revenue-by-state endpoints that read this table.
-- See docs/DECISIONS.md.
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS mart.daily_sales;

CREATE TABLE mart.daily_sales AS
SELECT
    purchase_date               AS date,
    purchase_month,
    customer_state,
    category,
    status,
    SUM(price)                  AS gmv,
    COUNT(DISTINCT order_id)    AS orders,
    COUNT(*)                    AS items,
    SUM(freight_value)          AS freight
FROM mart.order_item_facts
GROUP BY purchase_date, purchase_month, customer_state, category, status;

CREATE INDEX ds_date_idx     ON mart.daily_sales (date);
CREATE INDEX ds_month_idx    ON mart.daily_sales (purchase_month);
CREATE INDEX ds_state_idx    ON mart.daily_sales (customer_state);
CREATE INDEX ds_category_idx ON mart.daily_sales (category);
CREATE INDEX ds_status_idx   ON mart.daily_sales (status);
