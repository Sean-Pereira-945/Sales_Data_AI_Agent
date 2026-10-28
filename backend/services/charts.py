"""Deterministic, parameterized chart queries.

This is the no-AI data layer. Each function builds a read-only, fully
parameterized SQL statement from the global :class:`Filters` plus a few local
params, runs it against the ``mart.*`` tables, and returns small aggregated
rows (never raw order rows). Results are cached by ``hash(sql + params)``.

Source grain per chart (see docs/DECISIONS.md for the additive-vs-distinct
reasoning that drives these choices):
  * order_facts       — KPIs, trend, revenue-by-state, payment mix, delivery,
                        late %, review distribution
  * order_item_facts  — active-sellers KPI, category avg-review, seller Pareto
  * daily_sales       — top-categories (additive rollup; correct order counts
                        because an order maps to one row per category)
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import text

from api.filters import ALL_STATUSES, Filters
from app.config import get_settings
from db.session import read_only_session
from services.cache import query_cache

CURRENCY = "BRL"
MIN_ORDERS_DEFAULT = 30  # DASHBOARD_SPEC.md §4 rule 4

# Earliest date with real data; a prior period starting before this is not a
# valid comparison window (DASHBOARD_SPEC.md §4 rule 3).
DATA_FLOOR = date(2016, 9, 1)


def _run(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    """Execute a read-only query (statement-timeout guarded) and return rows."""
    def loader() -> list[dict[str, Any]]:
        timeout = int(get_settings().sql_statement_timeout_ms)
        with read_only_session() as session:
            session.execute(text(f"SET statement_timeout = {timeout}"))
            result = session.execute(text(sql), params)
            return [dict(r) for r in result.mappings()]

    return query_cache.cached(sql, params, loader)


def _and(clauses: list[str]) -> str:
    return " AND ".join(clauses)


# --------------------------------------------------------------------------- #
# Filter metadata
# --------------------------------------------------------------------------- #
def filters_meta() -> dict[str, Any]:
    """Allowed filter values and the data's date bounds."""
    def loader() -> dict[str, Any]:
        with read_only_session() as session:
            states = [r[0] for r in session.execute(
                text("SELECT DISTINCT customer_state FROM mart.order_facts ORDER BY 1"))]
            categories = [r[0] for r in session.execute(
                text("SELECT DISTINCT category FROM mart.order_item_facts ORDER BY 1"))]
            dmin, dmax = session.execute(
                text("SELECT MIN(purchase_date), MAX(purchase_date) FROM mart.order_facts")).one()
        return {
            "states": states,
            "categories": categories,
            "statuses": list(ALL_STATUSES),
            "date_min": str(dmin),
            "date_max": str(dmax),
            "default_date_from": str(Filters().date_from),
            "default_date_to": str(Filters().date_to),
            "default_statuses": Filters().statuses,
            "currency": CURRENCY,
        }

    return query_cache.cached("filters_meta", None, loader, ttl_seconds=3600)


# --------------------------------------------------------------------------- #
# KPI cards
# --------------------------------------------------------------------------- #
def kpis(f: Filters) -> dict[str, Any]:
    """Headline KPIs for the current period plus deltas vs the prior period."""
    def period_metrics(ff: Filters) -> dict[str, Any]:
        of_where, of_params = ff.where("order_facts")
        oif_where, oif_params = ff.where("order_item_facts")
        core = _run(
            f"""
            SELECT
                COALESCE(SUM(items_gmv), 0)                         AS gmv,
                COUNT(*)                                            AS orders,
                AVG(review_score)                                   AS avg_review,
                AVG(CASE WHEN is_late IS NULL THEN NULL
                         WHEN is_late THEN 0.0 ELSE 1.0 END)        AS on_time_rate
            FROM mart.order_facts
            WHERE {_and(of_where)}
            """,
            of_params,
        )[0]
        sellers = _run(
            f"SELECT COUNT(DISTINCT seller_id) AS active_sellers "
            f"FROM mart.order_item_facts WHERE {_and(oif_where)}",
            oif_params,
        )[0]
        gmv = float(core["gmv"] or 0)
        orders = int(core["orders"] or 0)
        return {
            "gmv": gmv,
            "orders": orders,
            "aov": (gmv / orders) if orders else 0.0,
            "avg_review": float(core["avg_review"]) if core["avg_review"] is not None else None,
            "on_time_pct": float(core["on_time_rate"]) * 100 if core["on_time_rate"] is not None else None,
            "active_sellers": int(sellers["active_sellers"] or 0),
        }

    current = period_metrics(f)
    prior_f, prior_label = _prior_period(f)
    prior = period_metrics(prior_f) if prior_f else None

    cards = []
    specs = [
        ("gmv", "GMV", CURRENCY, True),
        ("orders", "Orders", None, False),
        ("aov", "AOV", CURRENCY, True),
        ("avg_review", "Avg review", "stars", False),
        ("on_time_pct", "On-time %", "%", False),
        ("active_sellers", "Active sellers", None, False),
    ]
    for key, label, unit, _money in specs:
        cur = current.get(key)
        prev = prior.get(key) if prior else None
        delta_pct = None
        if prev not in (None, 0) and cur is not None:
            delta_pct = (cur - prev) / prev * 100
        cards.append({
            "key": key, "label": label, "unit": unit,
            "value": cur, "prev_value": prev, "delta_pct": delta_pct,
        })

    return {
        "cards": cards,
        "comparison_label": prior_label,
        "partial_period": f.partial_period(),
        "currency": CURRENCY,
    }


def _prior_period(f: Filters):
    """Return (Filters for the prior equal-length window, human label).

    Returns (None, reason) when the prior window would start before the dataset
    begins — a comparison against empty/sparse history is misleading, so we
    suppress it rather than report an absurd delta.
    """
    span = (f.date_to - f.date_from).days
    if span <= 0:
        return None, None
    prev_to = f.date_from - timedelta(days=1)
    prev_from = prev_to - timedelta(days=span)
    if prev_from < DATA_FLOOR:
        return None, "no comparable prior period (before data start)"
    prior = Filters(
        date_from=prev_from, date_to=prev_to,
        states=list(f.states), categories=list(f.categories), statuses=list(f.statuses),
    )
    return prior, f"{prev_from} – {prev_to}"


# --------------------------------------------------------------------------- #
# 1. GMV & Orders trend
# --------------------------------------------------------------------------- #
_GRANULARITY_SQL = {
    "day": "purchase_date",
    "week": "DATE_TRUNC('week', purchase_date)::DATE",
    "month": "purchase_month",
}


def trend(f: Filters, granularity: str = "month") -> dict[str, Any]:
    period = _GRANULARITY_SQL.get(granularity, _GRANULARITY_SQL["month"])
    where, params = f.where("order_facts")
    rows = _run(
        f"""
        SELECT {period} AS period,
               COALESCE(SUM(items_gmv), 0) AS gmv,
               COUNT(*)                    AS orders
        FROM mart.order_facts
        WHERE {_and(where)}
        GROUP BY 1
        ORDER BY 1
        """,
        params,
    )
    for r in rows:
        r["period"] = str(r["period"])
        r["gmv"] = float(r["gmv"] or 0)
        r["orders"] = int(r["orders"] or 0)
        r["aov"] = (r["gmv"] / r["orders"]) if r["orders"] else 0.0
    return {
        "data": rows,
        "meta": {"granularity": granularity, "currency": CURRENCY,
                 "partial_period": f.partial_period()},
    }


# --------------------------------------------------------------------------- #
# 2. Top categories
# --------------------------------------------------------------------------- #
def top_categories(f: Filters, top_n: int = 10, metric: str = "gmv") -> dict[str, Any]:
    top_n = max(1, min(int(top_n), 50))
    if metric == "avg_review":
        # Avg review per category, one review per (order, category); min-30 rule.
        oif_where, params = f.where("order_item_facts", alias="oif")
        params["min_orders"] = MIN_ORDERS_DEFAULT
        params["top_n"] = top_n
        rows = _run(
            f"""
            WITH per_order AS (
                SELECT DISTINCT oif.category, oif.order_id, of.review_score
                FROM mart.order_item_facts oif
                JOIN mart.order_facts of ON of.order_id = oif.order_id
                WHERE {_and(oif_where)} AND of.review_score IS NOT NULL
            )
            SELECT category,
                   AVG(review_score)        AS value,
                   COUNT(*)                 AS orders
            FROM per_order
            GROUP BY category
            HAVING COUNT(*) >= :min_orders
            ORDER BY value DESC
            LIMIT :top_n
            """,
            params,
        )
    else:
        where, params = f.where("daily_sales")
        params["top_n"] = top_n
        measure = {
            "gmv": "SUM(gmv)",
            "orders": "SUM(orders)",
            "aov": "SUM(gmv) / NULLIF(SUM(orders), 0)",
        }.get(metric, "SUM(gmv)")
        rows = _run(
            f"""
            SELECT category,
                   {measure}      AS value,
                   SUM(orders)    AS orders,
                   SUM(gmv)       AS gmv
            FROM mart.daily_sales
            WHERE {_and(where)}
            GROUP BY category
            ORDER BY value DESC NULLS LAST
            LIMIT :top_n
            """,
            params,
        )
    for r in rows:
        for k in ("value", "gmv"):
            if k in r and r[k] is not None:
                r[k] = float(r[k])
        if "orders" in r and r["orders"] is not None:
            r["orders"] = int(r["orders"])
    return {"data": rows, "meta": {"metric": metric, "top_n": top_n, "currency": CURRENCY}}


# --------------------------------------------------------------------------- #
# 3. Revenue by state
# --------------------------------------------------------------------------- #
def revenue_by_state(f: Filters, metric: str = "gmv") -> dict[str, Any]:
    where, params = f.where("order_facts")
    rows = _run(
        f"""
        SELECT customer_state                                      AS state,
               COALESCE(SUM(items_gmv), 0)                         AS gmv,
               COUNT(*)                                            AS orders,
               COALESCE(SUM(freight), 0)                           AS freight
        FROM mart.order_facts
        WHERE {_and(where)}
        GROUP BY customer_state
        ORDER BY gmv DESC
        """,
        params,
    )
    out = []
    for r in rows:
        gmv = float(r["gmv"] or 0)
        orders = int(r["orders"] or 0)
        freight = float(r["freight"] or 0)
        values = {
            "gmv": gmv,
            "orders": orders,
            "aov": (gmv / orders) if orders else 0.0,
            "freight_pct": (freight / gmv * 100) if gmv else 0.0,
        }
        out.append({"state": r["state"], "value": values.get(metric, gmv), **values})
    return {"data": out, "meta": {"metric": metric, "currency": CURRENCY}}


# --------------------------------------------------------------------------- #
# 4. Payment mix over time
# --------------------------------------------------------------------------- #
def payment_mix(f: Filters, view: str = "share") -> dict[str, Any]:
    where, params = f.where("order_facts")
    if view == "installments":
        rows = _run(
            f"""
            SELECT COALESCE(max_installments, 0) AS installments,
                   COUNT(*)                       AS orders,
                   AVG(items_gmv)                 AS avg_order_value
            FROM mart.order_facts
            WHERE {_and(where)} AND max_installments IS NOT NULL
            GROUP BY 1
            ORDER BY 1
            """,
            params,
        )
        for r in rows:
            r["installments"] = int(r["installments"])
            r["orders"] = int(r["orders"])
            r["avg_order_value"] = float(r["avg_order_value"] or 0)
        return {"data": rows, "meta": {"view": "installments", "currency": CURRENCY}}

    rows = _run(
        f"""
        SELECT purchase_month                     AS period,
               COALESCE(main_payment_type, 'unknown') AS payment_type,
               COUNT(*)                           AS orders,
               COALESCE(SUM(items_gmv), 0)        AS gmv
        FROM mart.order_facts
        WHERE {_and(where)}
        GROUP BY 1, 2
        ORDER BY 1, 2
        """,
        params,
    )
    for r in rows:
        r["period"] = str(r["period"])
        r["orders"] = int(r["orders"])
        r["gmv"] = float(r["gmv"] or 0)
    return {"data": rows, "meta": {"view": view, "currency": CURRENCY}}


# --------------------------------------------------------------------------- #
# 5. Delivery delay -> review score (headline)
# --------------------------------------------------------------------------- #
_BUCKET_ORDER = ["early", "on time", "1-3 days late", "4-7 days late", "8+ days late"]


def delay_vs_review(f: Filters) -> dict[str, Any]:
    where, params = f.where("order_facts")
    rows = _run(
        f"""
        SELECT delay_bucket,
               AVG(review_score) AS avg_review,
               COUNT(*)          AS orders
        FROM mart.order_facts
        WHERE {_and(where)}
          AND delay_bucket IS NOT NULL
          AND review_score IS NOT NULL
        GROUP BY delay_bucket
        """,
        params,
    )
    by_bucket = {r["delay_bucket"]: r for r in rows}
    data = []
    for bucket in _BUCKET_ORDER:
        r = by_bucket.get(bucket)
        data.append({
            "delay_bucket": bucket,
            "avg_review": float(r["avg_review"]) if r and r["avg_review"] is not None else None,
            "orders": int(r["orders"]) if r else 0,
        })
    return {"data": data, "meta": {"filter": "delivered orders with a review"}}


# --------------------------------------------------------------------------- #
# 6. Late % by state
# --------------------------------------------------------------------------- #
def late_by_state(f: Filters, min_orders: int = MIN_ORDERS_DEFAULT,
                  sort: str = "late_pct") -> dict[str, Any]:
    where, params = f.where("order_facts")
    params["min_orders"] = int(min_orders)
    rows = _run(
        f"""
        SELECT customer_state AS state,
               AVG(CASE WHEN is_late THEN 1.0 ELSE 0.0 END) * 100 AS late_pct,
               AVG(delivery_days)                                 AS avg_delivery_days,
               COUNT(*)                                           AS orders
        FROM mart.order_facts
        WHERE {_and(where)} AND is_late IS NOT NULL
        GROUP BY customer_state
        HAVING COUNT(*) >= :min_orders
        """,
        params,
    )
    for r in rows:
        r["late_pct"] = float(r["late_pct"] or 0)
        r["avg_delivery_days"] = float(r["avg_delivery_days"]) if r["avg_delivery_days"] is not None else None
        r["orders"] = int(r["orders"])
    key = {"late_pct": "late_pct", "delivery_days": "avg_delivery_days", "orders": "orders"}.get(sort, "late_pct")
    rows.sort(key=lambda r: (r[key] is None, r[key]), reverse=True)
    return {"data": rows, "meta": {"sort": sort, "min_orders": int(min_orders)}}


# --------------------------------------------------------------------------- #
# 7. Review score distribution
# --------------------------------------------------------------------------- #
def review_distribution(f: Filters, view: str = "distribution") -> dict[str, Any]:
    where, params = f.where("order_facts")
    if view == "trend":
        rows = _run(
            f"""
            SELECT purchase_month AS period,
                   AVG(review_score)                                           AS avg_review,
                   AVG(CASE WHEN review_score = 1 THEN 1.0 ELSE 0.0 END) * 100  AS one_star_pct,
                   COUNT(*)                                                     AS reviews
            FROM mart.order_facts
            WHERE {_and(where)} AND review_score IS NOT NULL
            GROUP BY 1
            ORDER BY 1
            """,
            params,
        )
        for r in rows:
            r["period"] = str(r["period"])
            r["avg_review"] = float(r["avg_review"]) if r["avg_review"] is not None else None
            r["one_star_pct"] = float(r["one_star_pct"] or 0)
            r["reviews"] = int(r["reviews"])
        return {"data": rows, "meta": {"view": "trend"}}

    rows = _run(
        f"""
        SELECT review_score AS score, COUNT(*) AS reviews
        FROM mart.order_facts
        WHERE {_and(where)} AND review_score IS NOT NULL
        GROUP BY review_score
        ORDER BY review_score
        """,
        params,
    )
    by_score = {int(r["score"]): int(r["reviews"]) for r in rows}
    data = [{"score": s, "reviews": by_score.get(s, 0)} for s in (1, 2, 3, 4, 5)]
    return {"data": data, "meta": {"view": "distribution"}}


# --------------------------------------------------------------------------- #
# 8. Seller concentration (Pareto)
# --------------------------------------------------------------------------- #
def seller_concentration(f: Filters, buckets: int = 20) -> dict[str, Any]:
    buckets = max(5, min(int(buckets), 100))
    where, params = f.where("order_item_facts")
    params["buckets"] = buckets
    rows = _run(
        f"""
        WITH seller_gmv AS (
            SELECT seller_id, SUM(price) AS gmv
            FROM mart.order_item_facts
            WHERE {_and(where)}
            GROUP BY seller_id
        ),
        ranked AS (
            SELECT seller_id, gmv,
                   SUM(gmv) OVER (ORDER BY gmv DESC
                                  ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cum_gmv,
                   SUM(gmv) OVER ()                                                  AS total_gmv,
                   PERCENT_RANK() OVER (ORDER BY gmv DESC)                           AS pct_rank
            FROM seller_gmv
        )
        SELECT LEAST(CAST(:buckets AS INT),
                     FLOOR(pct_rank * CAST(:buckets AS FLOAT))::INT + 1) AS bucket,
               MAX(cum_gmv) / NULLIF(MAX(total_gmv), 0) * 100 AS cum_gmv_pct,
               COUNT(*)                                       AS sellers
        FROM ranked
        GROUP BY bucket
        ORDER BY bucket
        """,
        params,
    )
    total_sellers = sum(int(r["sellers"]) for r in rows) or 1
    cum_sellers = 0
    data = []
    for r in rows:
        cum_sellers += int(r["sellers"])
        data.append({
            "seller_pct": round(cum_sellers / total_sellers * 100, 2),
            "cum_gmv_pct": float(r["cum_gmv_pct"]) if r["cum_gmv_pct"] is not None else None,
            "sellers": int(r["sellers"]),
        })
    return {"data": data, "meta": {"total_sellers": total_sellers, "currency": CURRENCY}}
