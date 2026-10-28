"""Dashboard API: one endpoint per chart plus KPI and filter-metadata routes.

All chart data is produced by the deterministic SQL layer in
``services/charts.py``. No LLM is involved in this module (Phase 1).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from api.filters import Filters, filter_params
from services import charts

router = APIRouter()


# --------------------------------------------------------------------------- #
# Filter metadata
# --------------------------------------------------------------------------- #
@router.get("/filters/meta", tags=["filters"])
def get_filters_meta() -> dict:
    """Allowed filter values (states, categories, statuses) and date bounds."""
    return charts.filters_meta()


# --------------------------------------------------------------------------- #
# KPI cards
# --------------------------------------------------------------------------- #
@router.get("/kpis", tags=["dashboard"])
def get_kpis(f: Filters = Depends(filter_params)) -> dict:
    return charts.kpis(f)


# --------------------------------------------------------------------------- #
# Charts
# --------------------------------------------------------------------------- #
@router.get("/charts/trend", tags=["charts"])
def chart_trend(
    f: Filters = Depends(filter_params),
    granularity: str = Query("month", pattern="^(day|week|month)$"),
) -> dict:
    return charts.trend(f, granularity=granularity)


@router.get("/charts/top-categories", tags=["charts"])
def chart_top_categories(
    f: Filters = Depends(filter_params),
    top_n: int = Query(10, ge=1, le=50),
    metric: str = Query("gmv", pattern="^(gmv|orders|aov|avg_review)$"),
) -> dict:
    return charts.top_categories(f, top_n=top_n, metric=metric)


@router.get("/charts/revenue-by-state", tags=["charts"])
def chart_revenue_by_state(
    f: Filters = Depends(filter_params),
    metric: str = Query("gmv", pattern="^(gmv|orders|aov|freight_pct)$"),
) -> dict:
    return charts.revenue_by_state(f, metric=metric)


@router.get("/charts/payment-mix", tags=["charts"])
def chart_payment_mix(
    f: Filters = Depends(filter_params),
    view: str = Query("share", pattern="^(share|absolute|installments)$"),
) -> dict:
    return charts.payment_mix(f, view=view)


@router.get("/charts/delay-vs-review", tags=["charts"])
def chart_delay_vs_review(f: Filters = Depends(filter_params)) -> dict:
    return charts.delay_vs_review(f)


@router.get("/charts/late-by-state", tags=["charts"])
def chart_late_by_state(
    f: Filters = Depends(filter_params),
    min_orders: int = Query(30, ge=0, le=1000),
    sort: str = Query("late_pct", pattern="^(late_pct|delivery_days|orders)$"),
) -> dict:
    return charts.late_by_state(f, min_orders=min_orders, sort=sort)


@router.get("/charts/review-distribution", tags=["charts"])
def chart_review_distribution(
    f: Filters = Depends(filter_params),
    view: str = Query("distribution", pattern="^(distribution|trend)$"),
) -> dict:
    return charts.review_distribution(f, view=view)


@router.get("/charts/seller-concentration", tags=["charts"])
def chart_seller_concentration(
    f: Filters = Depends(filter_params),
    buckets: int = Query(20, ge=5, le=100),
) -> dict:
    return charts.seller_concentration(f, buckets=buckets)
