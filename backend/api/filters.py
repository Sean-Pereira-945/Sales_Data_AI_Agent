"""Global dashboard filters and their SQL translation.

Every chart endpoint accepts the same global filters. Filter values are only
ever bound as query *parameters* (never string-formatted into SQL), so this
layer is injection-safe by construction.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from fastapi import Query

# Defaults from DASHBOARD_SPEC.md §4 / §6.
DEFAULT_DATE_FROM = date(2017, 1, 1)
DEFAULT_DATE_TO = date(2018, 8, 31)

ALL_STATUSES = (
    "approved", "canceled", "created", "delivered",
    "invoiced", "processing", "shipped", "unavailable",
)
# "Revenue-eligible" = everything except canceled / unavailable.
REVENUE_ELIGIBLE_STATUSES = tuple(s for s in ALL_STATUSES if s not in ("canceled", "unavailable"))

# Column names per mart grain.
_DATE_COL = {
    "daily_sales": "date",
    "order_facts": "purchase_date",
    "order_item_facts": "purchase_date",
}


@dataclass
class Filters:
    """Resolved global filters, ready to translate to SQL fragments."""

    date_from: date = DEFAULT_DATE_FROM
    date_to: date = DEFAULT_DATE_TO
    states: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    statuses: list[str] = field(default_factory=lambda: list(REVENUE_ELIGIBLE_STATUSES))

    def where(self, grain: str, alias: str = "") -> tuple[list[str], dict]:
        """Return (clauses, params) for the given mart grain.

        ``grain`` is one of 'daily_sales', 'order_facts', 'order_item_facts'.
        ``alias`` optionally prefixes column references (e.g. "f").
        """
        if grain not in _DATE_COL:
            raise ValueError(f"unknown grain: {grain}")
        p = f"{alias}." if alias else ""
        clauses: list[str] = []
        params: dict = {
            "date_from": self.date_from,
            "date_to": self.date_to,
        }

        clauses.append(f"{p}{_DATE_COL[grain]} BETWEEN :date_from AND :date_to")

        if self.states:
            clauses.append(f"{p}customer_state = ANY(:states)")
            params["states"] = self.states

        if self.statuses:
            clauses.append(f"{p}status = ANY(:statuses)")
            params["statuses"] = self.statuses

        if self.categories:
            if grain == "order_facts":
                # Order grain has no category column; an order matches if it
                # contains at least one item in a selected category (semijoin,
                # no fan-out on the order-level measures).
                clauses.append(
                    f"EXISTS (SELECT 1 FROM mart.order_item_facts oif "
                    f"WHERE oif.order_id = {p}order_id AND oif.category = ANY(:categories))"
                )
            else:
                clauses.append(f"{p}category = ANY(:categories)")
            params["categories"] = self.categories

        return clauses, params

    def partial_period(self) -> bool:
        """True when the range reaches into the sparse/truncated edges."""
        return self.date_from < DEFAULT_DATE_FROM or self.date_to > DEFAULT_DATE_TO


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def filter_params(
    date_from: date = Query(DEFAULT_DATE_FROM, description="Inclusive start date"),
    date_to: date = Query(DEFAULT_DATE_TO, description="Inclusive end date"),
    states: str | None = Query(None, description="Comma-separated customer states, e.g. SP,RJ"),
    categories: str | None = Query(None, description="Comma-separated category names (English)"),
    statuses: str | None = Query(
        None, description="Comma-separated order statuses; default = revenue-eligible"
    ),
) -> Filters:
    """FastAPI dependency that parses the global filters from query params."""
    status_list = _split_csv(statuses)
    # Ignore unknown statuses rather than erroring (keeps the UI forgiving).
    status_list = [s for s in status_list if s in ALL_STATUSES]
    return Filters(
        date_from=date_from,
        date_to=date_to,
        states=_split_csv(states),
        categories=_split_csv(categories),
        statuses=status_list or list(REVENUE_ELIGIBLE_STATUSES),
    )
