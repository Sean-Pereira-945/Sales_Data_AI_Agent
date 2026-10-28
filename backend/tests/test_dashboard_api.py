"""Endpoint tests for the Phase 1 dashboard API."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_filters_meta():
    meta = client.get("/api/filters/meta").json()
    assert "SP" in meta["states"]
    assert len(meta["states"]) == 27
    assert len(meta["categories"]) > 50
    assert meta["currency"] == "BRL"
    assert meta["date_min"] <= meta["date_max"]
    assert "canceled" not in meta["default_statuses"]


def test_kpis_shape_and_values():
    data = client.get("/api/kpis").json()
    cards = {c["key"]: c for c in data["cards"]}
    assert set(cards) == {"gmv", "orders", "aov", "avg_review", "on_time_pct", "active_sellers"}
    # GMV over the default revenue-eligible window is in the expected band.
    assert 12_000_000 <= cards["gmv"]["value"] <= 14_000_000
    assert 90_000 <= cards["orders"]["value"] <= 99_441
    assert 3.5 <= cards["avg_review"]["value"] <= 4.5
    assert 0 <= cards["on_time_pct"]["value"] <= 100
    # The default full-range window has no valid prior period, so the comparison
    # is suppressed rather than reported as an absurd delta.
    assert cards["gmv"]["delta_pct"] is None
    assert "no comparable" in data["comparison_label"]


def test_kpis_delta_on_valid_prior_period():
    # A narrower window has a real, in-data prior period.
    data = client.get(
        "/api/kpis", params={"date_from": "2018-01-01", "date_to": "2018-06-30"}
    ).json()
    cards = {c["key"]: c for c in data["cards"]}
    assert cards["gmv"]["delta_pct"] is not None
    assert cards["gmv"]["prev_value"] is not None
    assert data["comparison_label"].startswith("2017-")


@pytest.mark.parametrize("granularity", ["day", "week", "month"])
def test_trend(granularity):
    data = client.get("/api/charts/trend", params={"granularity": granularity}).json()
    assert data["meta"]["granularity"] == granularity
    assert len(data["data"]) > 0
    first = data["data"][0]
    assert {"period", "gmv", "orders", "aov"} <= set(first)


def test_top_categories_and_min_order_rule():
    data = client.get("/api/charts/top-categories", params={"top_n": 5, "metric": "gmv"}).json()
    assert len(data["data"]) == 5
    gmvs = [r["value"] for r in data["data"]]
    assert gmvs == sorted(gmvs, reverse=True)
    # Avg-review metric enforces the 30-order minimum.
    rev = client.get("/api/charts/top-categories", params={"metric": "avg_review"}).json()
    assert all(r["orders"] >= 30 for r in rev["data"])


def test_revenue_by_state_sp_leads():
    data = client.get("/api/charts/revenue-by-state").json()
    assert data["data"][0]["state"] == "SP"  # São Paulo dominates
    assert data["data"][0]["gmv"] > 0


def test_payment_mix_views():
    share = client.get("/api/charts/payment-mix", params={"view": "share"}).json()
    types = {r["payment_type"] for r in share["data"]}
    assert "credit_card" in types
    inst = client.get("/api/charts/payment-mix", params={"view": "installments"}).json()
    assert inst["meta"]["view"] == "installments"
    assert all("installments" in r for r in inst["data"])


def test_delay_vs_review_headline():
    data = client.get("/api/charts/delay-vs-review").json()
    by_bucket = {r["delay_bucket"]: r for r in data["data"]}
    assert len(data["data"]) == 5
    assert by_bucket["8+ days late"]["avg_review"] < by_bucket["early"]["avg_review"]


def test_late_by_state_min_orders():
    data = client.get("/api/charts/late-by-state", params={"min_orders": 30}).json()
    assert all(r["orders"] >= 30 for r in data["data"])
    assert all(0 <= r["late_pct"] <= 100 for r in data["data"])


def test_review_distribution():
    dist = client.get("/api/charts/review-distribution").json()
    scores = [r["score"] for r in dist["data"]]
    assert scores == [1, 2, 3, 4, 5]
    trend = client.get("/api/charts/review-distribution", params={"view": "trend"}).json()
    assert trend["meta"]["view"] == "trend"


def test_seller_concentration_is_monotonic():
    data = client.get("/api/charts/seller-concentration").json()
    cum = [r["cum_gmv_pct"] for r in data["data"] if r["cum_gmv_pct"] is not None]
    assert cum == sorted(cum)  # cumulative share only rises
    assert cum[-1] == pytest.approx(100, abs=1.0)


def test_filters_apply():
    """A state filter restricts results; an impossible filter yields empties."""
    sp = client.get("/api/charts/revenue-by-state", params={"states": "SP"}).json()
    assert [r["state"] for r in sp["data"]] == ["SP"]
    # Unknown state binds safely as a param and returns no rows (no SQL error).
    none = client.get("/api/charts/revenue-by-state", params={"states": "ZZ"}).json()
    assert none["data"] == []


def test_partial_period_flag():
    wide = client.get("/api/kpis", params={"date_from": "2016-01-01", "date_to": "2018-12-31"}).json()
    assert wide["partial_period"] is True
    narrow = client.get("/api/kpis").json()
    assert narrow["partial_period"] is False
