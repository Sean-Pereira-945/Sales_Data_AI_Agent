"""Report endpoints: generate a Markdown + PDF report, then download either.

POST /api/reports accepts a topic (e.g. "Q3 regional performance") plus the same
global filters as the dashboard; the report is built from the deterministic chart
queries with server-rendered charts and an LLM-written narrative.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel

from api.filters import Filters, filter_params
from services import report_builder

router = APIRouter()


class ReportRequest(BaseModel):
    topic: str = "Sales overview"


@router.post("/reports", tags=["reports"])
def create_report(req: ReportRequest, f: Filters = Depends(filter_params)) -> dict:
    r = report_builder.build_report(req.topic, f)
    return {
        "id": r.id,
        "title": r.title,
        "topic": r.topic,
        "created_at": r.created_at,
        "sections": r.section_titles,
        "markdown": r.markdown,
        "pdf_url": f"/api/reports/{r.id}.pdf",
        "markdown_url": f"/api/reports/{r.id}.md",
    }


@router.get("/reports/{report_id}.pdf", tags=["reports"])
def report_pdf(report_id: str) -> Response:
    r = report_builder.get_report(report_id)
    if r is None:
        raise HTTPException(status_code=404, detail="report not found (reports are kept in memory)")
    return Response(
        content=r.pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="report-{report_id}.pdf"'},
    )


@router.get("/reports/{report_id}.md", tags=["reports"])
def report_markdown(report_id: str) -> PlainTextResponse:
    r = report_builder.get_report(report_id)
    if r is None:
        raise HTTPException(status_code=404, detail="report not found (reports are kept in memory)")
    return PlainTextResponse(
        r.markdown,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="report-{report_id}.md"'},
    )
