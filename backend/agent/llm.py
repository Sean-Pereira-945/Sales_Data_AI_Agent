"""Provider-agnostic LLM wrapper.

Model name, provider and API key come from `.env` (never hardcoded). When a real
key is configured the agent calls the selected provider; when it is not, it
falls back to a deterministic **stub** so the whole graph — routing, SQL
generation, execution, analysis, insight — still runs offline (for the CLI and
tests).
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Protocol

from app.config import get_settings

logger = logging.getLogger(__name__)

# Default model if LLM_MODEL is unset (overridable via .env).
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"

# Per-call request timeout (ms) so a hung LLM call fails fast instead of blocking
# the whole agent run (see ARCHITECTURE_REVIEW.md §4).
LLM_TIMEOUT_MS = 30_000
# On a quota/unavailable error, stop calling the provider for this long and serve
# the deterministic stub instead — a lightweight circuit breaker that keeps the
# product responsive during a 429 (see ARCHITECTURE_REVIEW.md §3).
BREAKER_COOLDOWN_SECONDS = 300
# Transient (503/overloaded) errors get a couple of short backoff retries.
MAX_TRANSIENT_RETRIES = 2

Purpose = str  # "intent" | "sql" | "chart_spec" | "insight"


def _error_kind(exc: Exception) -> str:
    """Classify a provider error as 'quota', 'transient', or 'other'."""
    msg = str(exc).lower()
    if "429" in msg or "resource_exhausted" in msg or "quota" in msg or "rate limit" in msg:
        return "quota"
    if "503" in msg or "500" in msg or "unavailable" in msg or "overloaded" in msg or "deadline" in msg:
        return "transient"
    return "other"


class LLMClient(Protocol):
    def complete(self, system: str, user: str, *, purpose: Purpose = "", max_tokens: int = 2048) -> str: ...

    @property
    def name(self) -> str: ...


# --------------------------------------------------------------------------- #
# Gemini
# --------------------------------------------------------------------------- #
class GeminiLLM:
    def __init__(self, model: str, api_key: str) -> None:
        from google import genai
        from google.genai import types

        self._model = model or DEFAULT_GEMINI_MODEL
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=LLM_TIMEOUT_MS),
        )
        self._types = types
        self._fallback = StubLLM()
        # Circuit-breaker state: when > now(), skip the provider and use the stub.
        self._breaker_until = 0.0

    @property
    def name(self) -> str:
        return f"gemini:{self._model}"

    @property
    def degraded(self) -> bool:
        """True while the breaker is open (serving the stub, not the provider)."""
        return time.monotonic() < self._breaker_until

    def _call(self, system: str, user: str, max_tokens: int) -> str:
        response = self._client.models.generate_content(
            model=self._model,
            contents=user,
            config=self._types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=max_tokens,
            ),
        )
        return (response.text or "").strip()

    def complete(self, system: str, user: str, *, purpose: Purpose = "", max_tokens: int = 2048) -> str:
        # Breaker open → don't spend a call on a provider we know is failing.
        if self.degraded:
            return self._fallback.complete(system, user, purpose=purpose, max_tokens=max_tokens)

        for attempt in range(MAX_TRANSIENT_RETRIES + 1):
            try:
                text = self._call(system, user, max_tokens)
                if purpose == "summary" and not _has_summary_structure(text):
                    logger.warning("Gemini returned an incomplete summary; using deterministic fallback")
                    break
                if text:
                    return text
                logger.warning("Gemini returned an empty response; using deterministic fallback")
                break
            except Exception as exc:  # noqa: BLE001 - preserve dashboard/chat availability
                kind = _error_kind(exc)
                if kind == "quota":
                    # Don't hammer a quota-exhausted model: trip the breaker.
                    self._breaker_until = time.monotonic() + BREAKER_COOLDOWN_SECONDS
                    logger.warning(
                        "Gemini quota exhausted; serving deterministic fallback for %ss",
                        BREAKER_COOLDOWN_SECONDS,
                    )
                    break
                if kind == "transient" and attempt < MAX_TRANSIENT_RETRIES:
                    time.sleep(0.5 * (2**attempt))  # 0.5s, 1s backoff
                    continue
                logger.warning("Gemini request failed (%s); using deterministic fallback", type(exc).__name__)
                break
        return self._fallback.complete(system, user, purpose=purpose, max_tokens=max_tokens)


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
        if not facts:
            return "I couldn't find any matching data for that question."
        head = facts[0].rstrip(".")
        if len(facts) == 1:
            return (
                f"The data shows that {head[0].lower() + head[1:]}. "
                "There is no additional breakdown available for this view."
            )
        next_fact = facts[1].rstrip(".")
        return (
            f"The data shows that {head[0].lower() + head[1:]}. "
            f"This is followed by {next_fact[0].lower() + next_fact[1:]}. "
            "That pattern is worth monitoring as the filters change."
        )

    @staticmethod
    def _summary(user: str) -> str:
        m = re.search(r"FACTS:\s*(.*)", user, re.DOTALL)
        lines = [ln.strip("- ").strip() for ln in (m.group(1).strip().splitlines() if m else []) if ln.strip()]
        drivers = lines[:3] or ["No data for the current filters."]
        return (
            "Headline: Dashboard summary for the current filters.\n"
            "Drivers:\n" + "\n".join(f"- {d}" for d in drivers) + "\n"
            "Risk: Review the partial-period and low-volume caveats before acting.\n"
            "Recommendation: Open the chart with the largest movement to investigate."
        )


def _has_summary_structure(text: str) -> bool:
    """Require every section expected by dashboard and document consumers."""
    return all(
        marker in text
        for marker in ("Headline:", "Drivers:", "Risk:", "Recommendation:")
    )


# --------------------------------------------------------------------------- #
# Factory
# --------------------------------------------------------------------------- #
_llm: LLMClient | None = None


def get_llm() -> LLMClient:
    global _llm
    if _llm is None:
        s = get_settings()
        if s.llm_api_key and s.llm_provider == "gemini":
            _llm = GeminiLLM(model=s.llm_model, api_key=s.llm_api_key)
        else:
            _llm = StubLLM()
    return _llm


def reset_llm_cache() -> None:
    """Testing helper."""
    global _llm
    _llm = None


def llm_degraded() -> bool:
    """True when the LLM is running on the deterministic fallback.

    Either no provider key is configured (stub), or the circuit breaker is open
    after a quota/availability error. The API surfaces this so the UI can tell
    the user AI answers are temporarily degraded.
    """
    client = get_llm()
    if client.name.startswith("stub"):
        return True
    return bool(getattr(client, "degraded", False))
