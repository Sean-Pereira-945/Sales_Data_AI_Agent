"""Phase 5 report tests: planning, generation, and downloads."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from services import report_builder
from services.report_builder import plan_report, plan_sections

client = TestClient(app)


class _FakeLLM:
    """Scripted LLM so the live (non-stub) report path can be tested offline."""

    name = "fake:test"

    def complete(self, system: str, user: str, *, purpose: str = "", max_tokens: int = 2048) -> str:
        if purpose == "report_outline":
            return json.dumps(
                [
                    {"source": "catalog", "id": "trend"},
                    {"source": "custom", "title": "Orders by state",
                     "question": "number of orders by customer state"},
                    {"source": "bogus", "id": "nope"},          # ignored
                    {"source": "catalog", "id": "not_a_real_id"},  # ignored
                ]
            )
        if purpose == "sql":
            return (
                "SELECT customer_state AS state, COUNT(*) AS orders "
                "FROM mart.order_facts WHERE status NOT IN ('canceled','unavailable') "
                "GROUP BY customer_state ORDER BY orders DESC LIMIT 27"
            )
        if purpose == "chart_spec":
            return json.dumps({"type": "bar", "x": "state", "y": "orders", "series": None})
        if purpose == "insight":
            return "Orders are concentrated in the largest states."
        if purpose == "summary":
            return (
                "Headline: Orders concentrate in a few states.\n"
                "Drivers:\n- a\n- b\n- c\nRisk: concentration.\n"
                "Recommendation: diversify."
            )
        return ""


@pytest.fixture(autouse=True)
def _stub_llm_by_default(monkeypatch):
    """Report tests must be deterministic and never hit the live provider.

    Defaults every test to the offline stub; `fake_llm` overrides it for the
    tests that exercise the live (non-stub) planning path.
    """
    from agent.llm import StubLLM

    monkeypatch.setattr("agent.llm._llm", StubLLM())
    yield


@pytest.fixture()
def fake_llm(monkeypatch):
    monkeypatch.setattr("agent.llm._llm", _FakeLLM())
    yield


def test_plan_sections_by_topic():
    assert "revenue_by_state" in plan_sections("Q3 regional performance")
    assert any("late" in s or "delay" in s for s in plan_sections("delivery and logistics"))
    assert "top_categories" in plan_sections("product category deep dive")
    assert plan_sections("AOV report categories") == ["category_aov", "trend_aov"]
    assert plan_sections("AOV report over sttes") == ["aov_by_state"]
    assert plan_sections("something generic") == ["trend", "top_categories", "revenue_by_state", "delay_vs_review"]
    assert len(plan_sections("regional")) <= 5


def test_plan_report_falls_back_to_catalog_on_stub(monkeypatch):
    from agent.llm import StubLLM

    monkeypatch.setattr("agent.llm._llm", StubLLM())
    specs = plan_report("Q3 regional performance", report_builder.Filters())
    assert specs and all(s.source == "catalog" for s in specs)
    assert any(s.catalog_id == "revenue_by_state" for s in specs)


def test_plan_report_mixes_catalog_and_custom(fake_llm):
    specs = plan_report("orders by state and the GMV trend", report_builder.Filters())
    assert [s.source for s in specs] == ["catalog", "custom"]
    assert specs[0].catalog_id == "trend"
    assert specs[1].question and specs[1].title == "Orders by state"


def test_dynamic_report_has_multiple_sections(fake_llm):
    r = client.post("/api/reports", json={"topic": "orders by state and GMV trend"}).json()
    titles = r["sections"]
    assert len(titles) >= 2                       # not collapsed to a single chart
    assert "GMV (R$), monthly" in titles          # reliable catalog section
    assert "Orders by state" in titles            # LLM-planned custom section
    assert client.get(r["pdf_url"]).status_code == 200


def test_create_and_download_report():
    r = client.post("/api/reports", json={"topic": "Q3 regional performance"}).json()
    assert r["id"] and r["sections"]
    assert "Revenue by state (R$)" in r["sections"]
    assert "data:image/png;base64," in r["markdown"]       # self-contained charts
    assert r["markdown"].startswith("# Sales Intelligence Report")

    pdf = client.get(r["pdf_url"])
    assert pdf.status_code == 200
    assert pdf.content[:5] == b"%PDF-" and len(pdf.content) > 2000
    assert "attachment" in pdf.headers.get("content-disposition", "")

    md = client.get(r["markdown_url"])
    assert md.status_code == 200
    assert md.headers["content-type"].startswith("text/markdown")


def test_report_respects_filters():
    # A single-state filter still produces a valid report.
    r = client.post("/api/reports", params={"states": "SP"}, json={"topic": "overview"}).json()
    assert r["id"] and client.get(r["pdf_url"]).status_code == 200


def test_report_not_found():
    assert client.get("/api/reports/doesnotexist.pdf").status_code == 404
    assert client.get("/api/reports/doesnotexist.md").status_code == 404


def test_chat_report_intent_returns_report_id():
    with client.stream("POST", "/api/chat", json={"message": "generate a report on categories"}) as s:
        events = [json.loads(line[6:]) for line in s.iter_lines() if line.startswith("data: ")]
    final = events[-1]
    assert final["intent"] == "report"
    assert final["report_id"]
    assert client.get(f"/api/reports/{final['report_id']}.pdf").status_code == 200
