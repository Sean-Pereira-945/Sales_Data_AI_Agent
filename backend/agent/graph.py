"""LangGraph assembly: nodes + conditional edges + checkpointer.

Flow (see docs/ARCHITECTURE.md for the diagram):

    intent_router → schema_context → sql_generator → sql_validator ─┬─ ok ──→ executor ─┬─ ok ──→ analyzer → chart_spec → insight_writer → END
                                          ▲                          │                   │
                                          └────── retry (<3) ────────┴───────────────────┘
                                                          └─ exhausted ─→ fail → END
"""
from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from agent import nodes
from agent.state import MAX_RETRIES, AgentState


def _after_validation(state: AgentState) -> str:
    if not state.get("error"):
        return "execute"
    return "retry" if state.get("retries", 0) < MAX_RETRIES else "fail"


def _after_execution(state: AgentState) -> str:
    if not state.get("error"):
        return "analyze"
    return "retry" if state.get("retries", 0) < MAX_RETRIES else "fail"


def _after_intent(state: AgentState) -> str:
    return "report" if state.get("intent") == "report" else "query"


def build_graph(checkpointer=None):
    g = StateGraph(AgentState)

    g.add_node("intent_router", nodes.intent_router)
    g.add_node("schema_context", nodes.schema_context)
    g.add_node("sql_generator", nodes.sql_generator)
    g.add_node("sql_validator", nodes.sql_validator_node)
    g.add_node("executor", nodes.executor)
    g.add_node("analyzer", nodes.analyzer)
    g.add_node("chart_spec", nodes.chart_spec_node)
    g.add_node("insight_writer", nodes.insight_writer)
    g.add_node("report_composer", nodes.report_composer)
    g.add_node("fail", nodes.fail)

    g.add_edge(START, "intent_router")
    g.add_conditional_edges(
        "intent_router",
        _after_intent,
        {"report": "report_composer", "query": "schema_context"},
    )
    g.add_edge("report_composer", END)
    g.add_edge("schema_context", "sql_generator")
    g.add_edge("sql_generator", "sql_validator")

    g.add_conditional_edges(
        "sql_validator",
        _after_validation,
        {"execute": "executor", "retry": "sql_generator", "fail": "fail"},
    )
    g.add_conditional_edges(
        "executor",
        _after_execution,
        {"analyze": "analyzer", "retry": "sql_generator", "fail": "fail"},
    )

    g.add_edge("analyzer", "chart_spec")
    g.add_edge("chart_spec", "insight_writer")
    g.add_edge("insight_writer", END)
    g.add_edge("fail", END)

    return g.compile(checkpointer=checkpointer)


_agent = None


def get_agent():
    """Compiled graph with an in-memory checkpointer (thread_id → conversation)."""
    global _agent
    if _agent is None:
        _agent = build_graph(checkpointer=MemorySaver())
    return _agent


def ask(question: str, thread_id: str = "cli") -> AgentState:
    """Run one turn through the agent for the given conversation thread."""
    agent = get_agent()
    config = {"configurable": {"thread_id": thread_id}}
    return agent.invoke({"question": question}, config=config)
