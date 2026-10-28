"""Streaming chat endpoint backed by the LangGraph agent.

Streams Server-Sent Events: a `status` event per graph node, then one `final`
event with the answer, the validated SQL, an optional chart spec, and a capped
set of the aggregated rows (for an inline chart). Conversation memory is the
agent's checkpointer, keyed by `thread_id`.
"""
from __future__ import annotations

import datetime as dt
import json
import uuid
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent.graph import get_agent, run_config
from agent.llm import llm_degraded

router = APIRouter()

# Cap untrusted chat input to bound cost/DoS (see ARCHITECTURE_REVIEW.md §2).
MAX_MESSAGE_CHARS = 4000

_STAGE = {
    "intent_router": "routing",
    "sql_generator": "writing SQL",
    "sql_validator": "checking SQL",
    "executor": "running query",
    "analyzer": "analyzing",
    "chart_spec": "preparing chart",
    "insight_writer": "writing answer",
    "fail": "finishing",
}


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    thread_id: str | None = None


def _jsonable(v: Any) -> Any:
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    return v


def _rows(rows: list[dict[str, Any]], cap: int = 60) -> list[dict[str, Any]]:
    return [{k: _jsonable(x) for k, x in r.items()} for r in rows[:cap]]


@router.post("/chat", tags=["chat"])
def chat(req: ChatRequest) -> StreamingResponse:
    thread_id = req.thread_id or f"web-{uuid.uuid4().hex[:8]}"
    agent = get_agent()
    config = run_config(thread_id)

    def sse(obj: dict[str, Any]) -> str:
        return f"data: {json.dumps(obj)}\n\n"

    def gen() -> Iterator[str]:
        final: dict[str, Any] = {}
        try:
            for update in agent.stream({"question": req.message}, config=config, stream_mode="updates"):
                for node, patch in update.items():
                    if patch:
                        final.update(patch)
                    stage = _STAGE.get(node)
                    if stage:
                        yield sse({"type": "status", "stage": stage})
        except Exception as exc:  # noqa: BLE001 - surface as an SSE error, not a 500 mid-stream
            yield sse({"type": "error", "message": str(exc).splitlines()[0][:300]})
            return
        yield sse({
            "type": "final",
            "thread_id": thread_id,
            "intent": final.get("intent"),
            "sql": final.get("sql"),
            "insight": final.get("insight", ""),
            "chart_spec": final.get("chart_spec"),
            "row_count": final.get("row_count", 0),
            "data": _rows(final.get("result") or []),
            "report_id": final.get("report_id"),
            "degraded": llm_degraded(),
        })

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
