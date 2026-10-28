"""Per-chart AI insights and the dashboard summary.

Insights are generated **only** from the aggregated rows a chart already returns
(the LLM never sees raw rows), are numbers-grounded via the shared analyzer, and
are cached by ``hash(chart_id + params)``. Falls back to the deterministic facts
if the LLM call fails.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent.llm import get_llm
from agent.nodes.analysis import summarize_rows
from agent.prompts import INSIGHT_SYSTEM, SUMMARY_SYSTEM
from api.filters import Filters
from services import charts
from services.cache import make_key, query_cache

INSIGHT_TTL = 600


def _filter_params(f: Filters) -> dict[str, Any]:
    return {
        "date_from": str(f.date_from), "date_to": str(f.date_to),
        "states": sorted(f.states), "categories": sorted(f.categories),
        "statuses": sorted(f.statuses),
    }


# chart_id -> (rows-provider, human hint for the prompt)
_CHARTS: dict[str, tuple[Callable[[Filters, dict], list[dict]], str]] = {
    "trend": (
        lambda f, l: charts.trend(f, granularity=l.get("granularity", "month"))["data"],
        "GMV (R$) and orders over time",
    ),
    "top-categories": (
        lambda f, l: charts.top_categories(f, top_n=int(l.get("top_n", 10)), metric=l.get("metric", "gmv"))["data"],
        "top product categories",
    ),
    "revenue-by-state": (
        lambda f, l: charts.revenue_by_state(f, metric=l.get("metric", "gmv"))["data"],
        "revenue by customer state",
    ),
    "payment-mix": (
        lambda f, l: charts.payment_mix(f, view=l.get("view", "share"))["data"],
        "payment-type mix over time",
    ),
    "delay-vs-review": (
        lambda f, l: charts.delay_vs_review(f)["data"],
        "average review score by delivery-delay bucket (the headline relationship)",
    ),
    "late-by-state": (
        lambda f, l: charts.late_by_state(f, min_orders=int(l.get("min_orders", 30)), sort=l.get("sort", "late_pct"))["data"],
        "late-delivery percentage by state",
    ),
    "review-distribution": (
        lambda f, l: charts.review_distribution(f, view=l.get("view", "distribution"))["data"],
        "distribution of review scores",
    ),
    "seller-concentration": (
        lambda f, l: charts.seller_concentration(f, buckets=int(l.get("buckets", 20)))["data"],
        "seller GMV concentration (Pareto / platform-dependency risk)",
    ),
}


def _write_insight(hint: str, facts: list[str]) -> str:
    user = f"Chart: {hint}.\nFACTS:\n" + "\n".join(facts)
    try:
        text = get_llm().complete(INSIGHT_SYSTEM, user, purpose="insight", max_tokens=400)
        return text or (facts[0] if facts else "No data for these filters.")
    except Exception:  # noqa: BLE001 - never let an LLM error break the dashboard
        return facts[0] if facts else "No data for these filters."


def chart_insight(chart_id: str, f: Filters, local: dict[str, Any] | None = None) -> dict[str, Any]:
    if chart_id not in _CHARTS:
        raise KeyError(chart_id)
    local = local or {}
    params = {**_filter_params(f), **{k: str(v) for k, v in local.items()}}

    def loader() -> dict[str, Any]:
        provider, hint = _CHARTS[chart_id]
        rows = provider(f, local)
        facts = summarize_rows(rows).get("facts", [])
        return {"chart_id": chart_id, "insight": _write_insight(hint, facts),
                "model": get_llm().name, "facts": facts}

    return query_cache.cached(make_key(f"insight:{chart_id}", params), params, loader, INSIGHT_TTL)


def _kpi_facts(f: Filters) -> list[str]:
    data = charts.kpis(f)
    facts = [f"Comparison period: {data.get('comparison_label')}."]
    for c in data["cards"]:
        delta = f", {c['delta_pct']:+.1f}% vs prior" if c.get("delta_pct") is not None else ""
        facts.append(f"{c['label']}={c['value']}{delta}")
    if data.get("partial_period"):
        facts.append("Partial period: edges of the date range are sparse/truncated.")
    return facts


def kpi_insight(f: Filters) -> dict[str, Any]:
    params = _filter_params(f)

    def loader() -> dict[str, Any]:
        facts = _kpi_facts(f)
        hint = "the six KPI cards vs the prior period — say which moved most and the likely driver"
        return {"chart_id": "kpis", "insight": _write_insight(hint, facts),
                "model": get_llm().name, "facts": facts}

    return query_cache.cached(make_key("insight:kpis", params), params, loader, INSIGHT_TTL)


def dashboard_summary(f: Filters) -> dict[str, Any]:
    """Headline / 3 drivers / 1 risk / 1 recommendation from KPIs + key charts."""
    params = _filter_params(f)

    def loader() -> dict[str, Any]:
        blocks: list[str] = ["KPIs:"] + _kpi_facts(f)
        for cid in ("trend", "top-categories", "delay-vs-review", "late-by-state"):
            provider, hint = _CHARTS[cid]
            facts = summarize_rows(provider(f, {})).get("facts", [])
            blocks.append(f"\n{hint}:")
            blocks.extend(facts)
        user = "FACTS:\n" + "\n".join(blocks)
        try:
            text = get_llm().complete(SUMMARY_SYSTEM, user, purpose="summary", max_tokens=600)
        except Exception:  # noqa: BLE001
            text = "Headline: summary unavailable (LLM error).\n" + "\n".join(blocks[:6])
        return {"summary": text, "model": get_llm().name}

    return query_cache.cached(make_key("summary", params), params, loader, INSIGHT_TTL)
