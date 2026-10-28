"""SQL-pipeline nodes: schema context, generation, validation, execution."""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text

from agent.llm import get_llm
from agent.prompts import SCHEMA_CONTEXT, SQL_RETRY_SUFFIX, SQL_SYSTEM
from agent.state import AgentState
from app.config import get_settings
from db.session import read_only_session
from guards.sql_validator import validate_sql

_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$", re.MULTILINE)


def _strip_fences(sql: str) -> str:
    return _FENCE.sub("", sql or "").strip().rstrip(";").strip()


def schema_context(state: AgentState) -> dict[str, Any]:
    """Inject the relevant schema (the mart layer) for the generator."""
    return {"schema_context": SCHEMA_CONTEXT}


def sql_generator(state: AgentState) -> dict[str, Any]:
    """NL → SQL. On a retry, feed back the previous SQL and the error."""
    user = ""
    history = state.get("messages") or []
    if history:
        recent = "\n".join(f"{m['role']}: {m['content']}" for m in history[-4:])
        user += f"Conversation so far (for follow-up context):\n{recent}\n\n"
    user += f"Question: {state['question']}"

    if state.get("error") and state.get("raw_sql"):
        user += "\n\n" + SQL_RETRY_SUFFIX.format(sql=state["raw_sql"], error=state["error"])

    sql = get_llm().complete(SQL_SYSTEM, user, purpose="sql", max_tokens=1024)
    return {"raw_sql": _strip_fences(sql)}


def sql_validator_node(state: AgentState) -> dict[str, Any]:
    """Run the guard. Pass → sanitized SQL; fail → error + bumped retry count."""
    result = validate_sql(state.get("raw_sql", ""))
    if result.ok:
        return {"sql": result.sql, "error": None}
    return {"error": f"SQL rejected by guard: {result.reason}", "retries": state.get("retries", 0) + 1}


def executor(state: AgentState) -> dict[str, Any]:
    """Execute the validated SQL read-only, with a statement timeout."""
    timeout = int(get_settings().sql_statement_timeout_ms)
    try:
        with read_only_session() as session:
            session.execute(text(f"SET statement_timeout = {timeout}"))
            rows = session.execute(text(state["sql"])).mappings().all()
        data = [dict(r) for r in rows]
        return {"result": data, "row_count": len(data), "error": None}
    except Exception as exc:  # noqa: BLE001 - feed the DB error back to the generator
        msg = str(exc).splitlines()[0][:300]
        return {"error": f"execution error: {msg}", "retries": state.get("retries", 0) + 1}
