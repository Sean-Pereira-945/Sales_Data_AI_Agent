"""Report composer node — the 'report' intent branch.

Plans sections, runs the deterministic chart queries, renders charts, writes the
narrative, and builds Markdown + PDF (see services/report_builder.py). Reuses the
same aggregation + insight building blocks as the single-question pipeline.
"""
from __future__ import annotations

from typing import Any

from agent.state import AgentState
from api.filters import Filters
from services import report_builder


def report_composer(state: AgentState) -> dict[str, Any]:
    topic = state.get("question", "Sales overview")
    # The agent/CLI/chat path uses the default analysis window; the dashboard's
    # "Generate report" endpoint passes the user's current filters instead.
    result = report_builder.build_report(topic, Filters())
    insight = (
        f"Report ready: “{result.title}” with {len(result.section_titles)} sections "
        f"({', '.join(result.section_titles)}). Download the PDF or Markdown."
    )
    return {
        "report_id": result.id,
        "report_sections": [{"title": t} for t in result.section_titles],
        "insight": insight,
    }
