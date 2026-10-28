"""End-to-end agent tests (stub LLM, real mart).

These run with the deterministic stub LLM (no API key needed), exercising the
full graph: route → schema → generate → validate → execute → analyze → insight.
"""
from __future__ import annotations

import uuid

import pytest

from agent.graph import build_graph
from agent.llm import StubLLM
from guards.sql_validator import validate_sql


@pytest.fixture()
def agent(monkeypatch):
    # Force the stub regardless of local .env, and give each test a fresh graph.
    monkeypatch.setattr("agent.llm._llm", StubLLM())
    from langgraph.checkpoint.memory import MemorySaver

    return build_graph(checkpointer=MemorySaver())


def _ask(agent, q, thread="t"):
    return agent.invoke({"question": q}, config={"configurable": {"thread_id": thread}})


def test_chart_question_runs_end_to_end(agent):
    s = _ask(agent, "show me the monthly GMV trend")
    assert s["intent"] == "chart"
    assert s["row_count"] > 0
    assert s["sql"] and validate_sql(s["sql"]).ok   # the executed SQL is guard-valid
    assert s["chart_spec"] and s["chart_spec"]["x"] in s["result"][0]
    assert s["insight"]


def test_qa_top_categories(agent):
    s = _ask(agent, "top categories by revenue")
    assert s["row_count"] >= 1
    assert "category" in s["result"][0]
    # Health & beauty is the top Olist category by GMV.
    assert s["result"][0]["category"] == "health_beauty"


def test_delay_headline(agent):
    s = _ask(agent, "how does delivery delay affect review score")
    buckets = {r["delay_bucket"]: float(r["avg_review"]) for r in s["result"]}
    assert buckets["8+ days late"] < buckets["early"]


def test_memory_accumulates_across_turns(agent):
    thread = f"mem-{uuid.uuid4().hex[:6]}"
    _ask(agent, "monthly gmv trend", thread)
    s2 = _ask(agent, "now only for sellers", thread)
    # Both turns are retained in the persisted conversation memory.
    assert len(s2["messages"]) >= 4


def test_result_rows_are_small(agent):
    """The LLM only ever sees aggregated results (<= the enforced LIMIT)."""
    s = _ask(agent, "revenue by state")
    assert s["row_count"] <= 200
