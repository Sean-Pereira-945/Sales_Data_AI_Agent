"""Phase 5 report tests: planning, generation, and downloads."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import app
from services.report_builder import plan_sections

client = TestClient(app)


def test_plan_sections_by_topic():
    assert "revenue_by_state" in plan_sections("Q3 regional performance")
    assert any("late" in s or "delay" in s for s in plan_sections("delivery and logistics"))
    assert "top_categories" in plan_sections("product category deep dive")
    assert plan_sections("something generic") == ["trend", "top_categories", "revenue_by_state", "delay_vs_review"]
    assert len(plan_sections("regional")) <= 5


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
