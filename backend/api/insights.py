"""AI insight endpoints: per-chart summaries, KPI insight, dashboard summary.

Same global filters as the dashboard; per-chart local params are accepted so the
insight matches exactly what the chart is showing. Results are cached.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from api.filters import Filters, filter_params
from services import insights

router = APIRouter()


@router.get("/insights/kpis", tags=["insights"])
def insights_kpis(f: Filters = Depends(filter_params)) -> dict:
    return insights.kpi_insight(f)


@router.get("/insights/summary", tags=["insights"])
def insights_summary(f: Filters = Depends(filter_params)) -> dict:
    """The 'Summarize dashboard' brief: headline, 3 drivers, 1 risk, 1 recommendation."""
    return insights.dashboard_summary(f)


@router.get("/insights/{chart_id}", tags=["insights"])
def insights_chart(
    chart_id: str,
    f: Filters = Depends(filter_params),
    # Union of per-chart local controls (only the relevant ones are used).
    granularity: str | None = Query(None),
    top_n: int | None = Query(None),
    metric: str | None = Query(None),
    view: str | None = Query(None),
    min_orders: int | None = Query(None),
    sort: str | None = Query(None),
    buckets: int | None = Query(None),
) -> dict:
    local = {k: v for k, v in {
        "granularity": granularity, "top_n": top_n, "metric": metric, "view": view,
        "min_orders": min_orders, "sort": sort, "buckets": buckets,
    }.items() if v is not None}
    try:
        return insights.chart_insight(chart_id, f, local)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown chart_id: {chart_id}") from None
