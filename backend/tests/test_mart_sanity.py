"""Sanity checks on the mart (DASHBOARD_SPEC.md §4).

A large deviation here indicates a fan-out or filter bug in db/views.sql.
These run against the live mart built by `python -m db.refresh_mart`.
"""
from __future__ import annotations

from sqlalchemy import text

from db.session import read_only_session


def _scalar(sql: str):
    with read_only_session() as s:
        return s.execute(text(sql)).scalar_one()


def test_total_orders_about_99k():
    assert _scalar("SELECT COUNT(*) FROM mart.order_facts") == 99441


def test_order_facts_one_row_per_order():
    assert _scalar("SELECT COUNT(*) FROM mart.order_facts") == _scalar(
        "SELECT COUNT(DISTINCT order_id) FROM mart.order_facts"
    )


def test_gmv_in_expected_band():
    gmv = float(_scalar(
        "SELECT SUM(items_gmv) FROM mart.order_facts "
        "WHERE status NOT IN ('canceled','unavailable')"
    ))
    assert 13_000_000 <= gmv <= 14_000_000


def test_avg_review_about_four():
    avg = float(_scalar(
        "SELECT AVG(review_score) FROM mart.order_facts WHERE review_score IS NOT NULL"
    ))
    assert 4.0 <= avg <= 4.1


def test_credit_card_share_70_to_80():
    pct = float(_scalar(
        "SELECT 100.0*SUM(CASE WHEN main_payment_type='credit_card' THEN 1 ELSE 0 END)/COUNT(*) "
        "FROM mart.order_facts WHERE main_payment_type IS NOT NULL"
    ))
    assert 70 <= pct <= 80


def test_headline_late_orders_score_lower():
    """The dashboard's headline: late delivery drives low review scores."""
    with read_only_session() as s:
        rows = {
            r[0]: float(r[1])
            for r in s.execute(text(
                "SELECT delay_bucket, AVG(review_score) FROM mart.order_facts "
                "WHERE review_score IS NOT NULL AND delay_bucket IS NOT NULL GROUP BY 1"
            ))
        }
    assert rows["8+ days late"] < rows["early"]
    assert rows["8+ days late"] < 2.5
    assert rows["early"] > 4.0


def test_no_item_fanout_in_gmv():
    """GMV via order grain equals GMV via item grain (no double counting)."""
    order_gmv = float(_scalar("SELECT SUM(items_gmv) FROM mart.order_facts"))
    item_gmv = float(_scalar("SELECT SUM(price) FROM mart.order_item_facts"))
    assert abs(order_gmv - item_gmv) < 1.0
