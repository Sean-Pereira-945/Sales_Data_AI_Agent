"""Intent routing node."""
from __future__ import annotations

import re
from typing import Any

from agent.llm import get_llm
from agent.prompts import INTENT_SYSTEM
from agent.state import AgentState

_VALID = ("qa", "chart", "summary", "report")


def intent_router(state: AgentState) -> dict[str, Any]:
    raw = get_llm().complete(INTENT_SYSTEM, state["question"], purpose="intent", max_tokens=16)
    token = raw.strip().lower()
    intent = next((v for v in _VALID if re.search(rf"\b{v}\b", token)), "qa")
    return {"intent": intent, "retries": 0, "error": None}
