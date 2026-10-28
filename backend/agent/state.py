"""Shared state for the LangGraph agent.

One TypedDict flows through every node; LangGraph's checkpointer persists it per
`thread_id` so follow-up questions ("now only for the West") see prior turns.
"""
from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    # Input
    question: str
    thread_id: str

    # Routing
    intent: str                       # qa | chart | summary | report
    filters: dict[str, Any]           # optional structured filters (follow-ups)

    # SQL pipeline
    schema_context: str               # relevant tables/columns injected into the prompt
    sql: str                          # validated, sanitized SQL
    raw_sql: str                      # the model's last proposal (pre-validation)
    result: list[dict[str, Any]]      # aggregated rows (never raw order rows)
    row_count: int
    error: str | None                 # validation/execution error fed back to the generator
    retries: int

    # Outputs
    analysis: dict[str, Any]          # deterministic deltas / top-N / anomalies
    chart_spec: dict[str, Any] | None
    insight: str
    report_sections: list[dict[str, Any]]   # Phase 5
    report_id: str

    # Conversation memory (persisted by the checkpointer)
    messages: list[dict[str, str]]


MAX_RETRIES = 3
