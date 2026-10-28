"""Phase 4 AI endpoints: per-chart insights, KPI insight, summary, chat stream.

Run with the stub LLM (no key) — deterministic, so assertions are stable.
"""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _events(message: str, thread_id: str | None = None) -> list[dict]:
    body = {"message": message}
    if thread_id:
        body["thread_id"] = thread_id
    with client.stream("POST", "/api/chat", json=body) as r:
        return [json.loads(line[6:]) for line in r.iter_lines() if line.startswith("data: ")]


def test_chart_insight():
    r = client.get("/api/insights/delay-vs-review").json()
    assert r["chart_id"] == "delay-vs-review"
    assert r["insight"]
    assert "8+ days late" in " ".join(r["facts"])


def test_chart_insight_with_local_params():
    r = client.get("/api/insights/top-categories", params={"top_n": 5, "metric": "gmv"}).json()
    assert r["insight"] and r["chart_id"] == "top-categories"


def test_kpi_insight():
    assert client.get("/api/insights/kpis").json()["insight"]


def test_summary_structure():
    s = client.get("/api/insights/summary").json()["summary"]
    assert "Headline" in s and "Recommendation" in s


def test_unknown_chart_404():
    assert client.get("/api/insights/nope").status_code == 404


def test_chat_streams_status_then_final():
    events = _events("show me the monthly gmv trend")
    assert events[0]["type"] == "status"
    final = events[-1]
    assert final["type"] == "final"
    assert final["intent"] == "chart"
    assert final["row_count"] > 0
    assert final["insight"]
    assert final["chart_spec"] and final["chart_spec"]["x"] in final["data"][0]


def test_chat_memory_shares_thread():
    tid = "pytest-thread"
    _events("monthly gmv trend", tid)
    final2 = _events("now top categories", tid)[-1]
    assert final2["type"] == "final" and final2["thread_id"] == tid
