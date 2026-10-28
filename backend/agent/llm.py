"""Provider-agnostic LLM wrapper.

Model name, provider and API key come from `.env` (never hardcoded). When a real
key is configured the agent calls Anthropic; when it is not, it falls back to a
deterministic **stub** so the whole graph — routing, SQL generation, execution,
analysis, insight — still runs offline (for the CLI and tests). The stub is a
test shim, not a second "model": it does keyword routing and picks from a small
set of SQL templates; the real NL→SQL quality comes from the Anthropic path.
"""
from __future__ import annotations

import json
import re
from typing import Protocol

from app.config import get_settings

# Default model if LLM_MODEL is unset (overridable via .env). Per the Anthropic
# guidance, default to the current Opus unless the user picks another.
DEFAULT_ANTHROPIC_MODEL = "claude-opus-5-5"

Purpose = str  # "intent" | "sql" | "chart_spec" | "insight"


class LLMClient(Protocol):
    def complete(self, system: str, user: str, *, purpose: Purpose = "", max_tokens: int = 2048) -> str: ...

    @property
    def name(self) -> str: ...


# --------------------------------------------------------------------------- #
# Anthropic
# --------------------------------------------------------------------------- #
class AnthropicLLM:
    def __init__(self, model: str, api_key: str) -> None:
        from anthropic import Anthropic

        self._model = model or DEFAULT_ANTHROPIC_MODEL
        self._client = Anthropic(api_key=api_key)

    @property
    def name(self) -> str:
        return f"anthropic:{self._model}"

    def complete(self, system: str, user: str, *, purpose: Purpose = "", max_tokens: int = 2048) -> str:
        # Plain (non-streaming) message. No temperature/thinking overrides — the
        # current Opus models reject non-default sampling and manage thinking
        # adaptively; small structured outputs don't need streaming.
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
        return "".join(parts).strip()


# --------------------------------------------------------------------------- #
# Deterministic offline stub
# --------------------------------------------------------------------------- #
_SQL_TEMPLATES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(trend|over time|monthly|per month|by month|growth)\b", re.IGNORECASE),
     "SELECT purchase_month AS month, SUM(gmv) AS gmv, SUM(orders) AS orders "
     "FROM mart.daily_sales "
     "WHERE status NOT IN ('canceled','unavailable') "
     "GROUP BY purchase_month ORDER BY purchase_month LIMIT 100"),
    (re.compile(r"\b(categor)", re.IGNORECASE),
     "SELECT category, SUM(gmv) AS gmv, SUM(orders) AS orders "
     "FROM mart.daily_sales "
     "WHERE status NOT IN ('canceled','unavailable') "
     "GROUP BY category ORDER BY gmv DESC LIMIT 10"),
    (re.compile(r"\b(late|delay|on[- ]?time|delivery)\b", re.IGNORECASE),
     "SELECT delay_bucket, AVG(review_score) AS avg_review, COUNT(*) AS orders "
     "FROM mart.order_facts "
     "WHERE delay_bucket IS NOT NULL AND review_score IS NOT NULL "
     "GROUP BY delay_bucket ORDER BY avg_review DESC LIMIT 10"),
    (re.compile(r"\b(review|score|rating|star)\b", re.IGNORECASE),
     "SELECT review_score AS score, COUNT(*) AS reviews "
     "FROM mart.order_facts WHERE review_score IS NOT NULL "
     "GROUP BY review_score ORDER BY review_score LIMIT 10"),
    (re.compile(r"\b(seller)", re.IGNORECASE),
     "SELECT seller_id, SUM(price) AS gmv FROM mart.order_item_facts "
     "GROUP BY seller_id ORDER BY gmv DESC LIMIT 10"),
    (re.compile(r"\b(payment|installment|boleto|credit)\b", re.IGNORECASE),
     "SELECT main_payment_type AS payment_type, COUNT(*) AS orders "
     "FROM mart.order_facts WHERE main_payment_type IS NOT NULL "
     "GROUP BY main_payment_type ORDER BY orders DESC LIMIT 10"),
    (re.compile(r"\b(state|region|geograph|where)\b", re.IGNORECASE),
     "SELECT customer_state AS state, SUM(items_gmv) AS gmv, COUNT(*) AS orders "
     "FROM mart.order_facts "
     "WHERE status NOT IN ('canceled','unavailable') "
     "GROUP BY customer_state ORDER BY gmv DESC LIMIT 27"),
]

_DEFAULT_SQL = (
    "SELECT COUNT(*) AS orders, SUM(items_gmv) AS gmv, AVG(review_score) AS avg_review "
    "FROM mart.order_facts WHERE status NOT IN ('canceled','unavailable') LIMIT 1"
)


class StubLLM:
    """Keyword/templated responses so the graph runs with no API key."""

    @property
    def name(self) -> str:
        return "stub (no LLM key configured)"

    def complete(self, system: str, user: str, *, purpose: Purpose = "", max_tokens: int = 2048) -> str:
        if purpose == "intent":
            return self._intent(user)
        if purpose == "sql":
            return self._sql(user)
        if purpose == "chart_spec":
            return self._chart_spec(user)
        if purpose == "insight":
            return self._insight(user)
        if purpose == "summary":
            return self._summary(user)
        return ""

    @staticmethod
    def _intent(question: str) -> str:
        q = question.lower()
        if re.search(r"\b(report|pdf|deck|write[- ]?up)\b", q):
            return "report"
        if re.search(r"\b(summar|overview|how are we|dashboard)\b", q):
            return "summary"
        if re.search(r"\b(chart|plot|graph|trend|bar|line|distribution|show me)\b", q):
            return "chart"
        return "qa"

    @staticmethod
    def _sql(user: str) -> str:
        # The question is passed after a "Question:" marker in the user prompt.
        m = re.search(r"Question:\s*(.*)", user, re.DOTALL)
        question = m.group(1) if m else user
        for pattern, sql in _SQL_TEMPLATES:
            if pattern.search(question):
                return sql
        return _DEFAULT_SQL

    @staticmethod
    def _chart_spec(user: str) -> str:
        # Pick axes from the column names listed in the prompt.
        cols = re.findall(r"columns:\s*\[([^\]]*)\]", user)
        names = [c.strip().strip("'\"") for c in cols[0].split(",")] if cols else []
        x = names[0] if names else "x"
        y = next((n for n in names[1:]), "y")
        ctype = "line" if x in ("month", "period", "date") else "bar"
        return json.dumps({"type": ctype, "x": x, "y": y, "series": None})

    @staticmethod
    def _insight(user: str) -> str:
        # The analyzer's facts are passed in the user prompt after "FACTS:".
        m = re.search(r"FACTS:\s*(.*)", user, re.DOTALL)
        facts = (m.group(1).strip() if m else "").splitlines()
        head = facts[0] if facts else "No rows returned."
        return f"{head} (deterministic summary — set LLM_API_KEY in .env for AI-written insights.)"

    @staticmethod
    def _summary(user: str) -> str:
        m = re.search(r"FACTS:\s*(.*)", user, re.DOTALL)
        lines = [ln.strip("- ").strip() for ln in (m.group(1).strip().splitlines() if m else []) if ln.strip()]
        drivers = lines[:3] or ["No data for the current filters."]
        return (
            "Headline: Dashboard summary for the current filters (deterministic — "
            "set LLM_API_KEY in .env for an AI-written brief).\n"
            "Drivers:\n" + "\n".join(f"- {d}" for d in drivers) + "\n"
            "Risk: Review the partial-period and low-volume caveats before acting.\n"
            "Recommendation: Open the chart with the largest movement to investigate."
        )


# --------------------------------------------------------------------------- #
# Factory
# --------------------------------------------------------------------------- #
_llm: LLMClient | None = None


def get_llm() -> LLMClient:
    global _llm
    if _llm is None:
        s = get_settings()
        if s.llm_provider == "anthropic" and s.llm_api_key:
            _llm = AnthropicLLM(model=s.llm_model, api_key=s.llm_api_key)
        else:
            _llm = StubLLM()
    return _llm


def reset_llm_cache() -> None:
    """Testing helper."""
    global _llm
    _llm = None
