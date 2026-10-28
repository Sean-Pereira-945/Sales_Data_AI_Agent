"""Deterministic analysis, chart-spec selection, and insight writing.

The analyzer computes deltas / top-N / simple anomalies in **Python** from the
already-aggregated rows (the LLM never does arithmetic). The insight writer turns
those facts into prose; every number it is allowed to use comes from here.
"""
from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal
from typing import Any

from agent.llm import get_llm
from agent.prompts import CHART_SPEC_SYSTEM, INSIGHT_SYSTEM
from agent.state import AgentState

_NUMERIC = (int, float, Decimal)
_BLACK_FRIDAY = dt.date(2017, 11, 24)


def _is_number(v: Any) -> bool:
    return isinstance(v, _NUMERIC) and not isinstance(v, bool)


def _num(v: Any) -> float:
    return float(v) if _is_number(v) else 0.0


def _columns(rows: list[dict[str, Any]]) -> tuple[list[str], list[str], str | None]:
    """Return (all_cols, numeric_cols, label_col)."""
    cols = list(rows[0].keys())
    numeric = [c for c in cols if any(_is_number(r.get(c)) for r in rows)]
    label = next((c for c in cols if c not in numeric), cols[0] if cols else None)
    return cols, numeric, label


def analyzer(state: AgentState) -> dict[str, Any]:
    return {"analysis": summarize_rows(state.get("result") or [])}


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic facts from aggregated rows — shared by the graph analyzer
    node and the dashboard insight endpoints. The LLM only ever sees these."""
    if not rows:
        return {"facts": ["No rows matched the query."], "n_rows": 0}

    cols, numeric, label = _columns(rows)
    facts: list[str] = []
    out: dict[str, Any] = {"n_rows": len(rows), "columns": cols}

    if len(rows) == 1:
        parts = [f"{c}={_fmt(rows[0][c])}" for c in cols]
        facts.append("; ".join(parts))
    elif numeric:
        measure = numeric[0]
        additive = _is_additive(measure)
        total = sum(_num(r.get(measure)) for r in rows)
        ranked = sorted(rows, key=lambda r: _num(r.get(measure)), reverse=True)
        top, bottom = ranked[0], ranked[-1]
        out["measure"] = measure
        if additive:
            out["total"] = total
            facts.append(
                f"{len(rows)} groups by '{label}'. Top by {measure}: "
                f"{top.get(label)}={_fmt(top.get(measure))}"
                + (f" ({_num(top.get(measure)) / total * 100:.1f}% of total)" if total else "")
                + f". Total {measure}={_fmt(total)}."
            )
        else:
            # Non-additive (avg/rate/score/pct): report range, never a sum.
            facts.append(
                f"{len(rows)} groups by '{label}'. Highest {measure}: "
                f"{top.get(label)}={_fmt(top.get(measure))}; lowest: "
                f"{bottom.get(label)}={_fmt(bottom.get(measure))}."
            )
        if len(ranked) >= 3:
            nxt = ", ".join(f"{r.get(label)} ({_fmt(r.get(measure))})" for r in ranked[1:3])
            facts.append(f"Next: {nxt}.")

        # Time-series change (first vs last) when the label looks temporal.
        if label and _looks_temporal(rows, label):
            ordered = sorted(rows, key=lambda r: str(r.get(label)))
            a, b = _num(ordered[0].get(measure)), _num(ordered[-1].get(measure))
            if a:
                facts.append(
                    f"{measure} changed {(b - a) / a * 100:+.1f}% from "
                    f"{ordered[0].get(label)} to {ordered[-1].get(label)}."
                )
            peak = max(ordered, key=lambda r: _num(r.get(measure)))
            facts.append(f"Peak {measure} at {peak.get(label)} ({_fmt(peak.get(measure))}).")
            if _covers_black_friday(rows, label):
                facts.append("Range includes Black Friday (24 Nov 2017).")

    return {"facts": facts, **out}


def chart_spec_node(state: AgentState) -> dict[str, Any]:
    """Pick a chart spec when the intent is 'chart'; validate it against columns."""
    if state.get("intent") != "chart":
        return {"chart_spec": None}
    rows = state.get("result") or []
    if not rows:
        return {"chart_spec": None}
    cols = list(rows[0].keys())
    user = f"Question: {state['question']}\ncolumns: [{', '.join(cols)}]"
    raw = get_llm().complete(CHART_SPEC_SYSTEM, user, purpose="chart_spec", max_tokens=200)
    spec = _safe_json(raw)
    if not isinstance(spec, dict) or spec.get("x") not in cols or spec.get("y") not in cols:
        # Fall back to a sane default from the column shapes.
        _, numeric, label = _columns(rows)
        spec = {
            "type": "line" if label and _looks_temporal(rows, label) else "bar",
            "x": label or cols[0],
            "y": (numeric[0] if numeric else cols[-1]),
            "series": None,
        }
    return {"chart_spec": spec}


def insight_writer(state: AgentState) -> dict[str, Any]:
    analysis = state.get("analysis") or {}
    facts = analysis.get("facts") or ["No data."]
    question = state.get("question", "")
    user = f"Question: {question}\n\nFACTS:\n" + "\n".join(facts)
    insight = get_llm().complete(INSIGHT_SYSTEM, user, purpose="insight", max_tokens=400)

    # Append this turn to conversation memory (persisted by the checkpointer).
    messages = list(state.get("messages") or [])
    messages.append({"role": "user", "content": question})
    messages.append({"role": "assistant", "content": insight})
    return {"insight": insight, "messages": messages}


def fail(state: AgentState) -> dict[str, Any]:
    """Graceful terminal when SQL couldn't be produced/executed after retries."""
    err = state.get("error") or "unknown error"
    return {
        "insight": f"Sorry — I couldn't answer that from the data ({err}). "
                   "Try rephrasing, or ask about GMV, orders, categories, states, "
                   "delivery delay, reviews, payments, or sellers.",
        "result": state.get("result") or [],
        "row_count": state.get("row_count", 0),
    }


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _fmt(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return str(v)
    if _is_number(v):
        f = float(v)
        return f"{f:,.2f}".rstrip("0").rstrip(".") if f % 1 else f"{int(f):,}"
    return str(v)


_NON_ADDITIVE = ("avg", "mean", "rate", "pct", "percent", "ratio", "score", "review", "aov")


def _is_additive(measure: str) -> bool:
    m = measure.lower()
    return not any(tok in m for tok in _NON_ADDITIVE)


def _looks_temporal(rows: list[dict[str, Any]], label: str) -> bool:
    if label.lower() in ("month", "period", "date", "day", "week", "purchase_month"):
        return True
    return any(isinstance(r.get(label), (dt.date, dt.datetime)) for r in rows)


def _covers_black_friday(rows: list[dict[str, Any]], label: str) -> bool:
    dates = [r.get(label) for r in rows if isinstance(r.get(label), (dt.date, dt.datetime))]
    if not dates:
        return False
    lo, hi = min(dates), max(dates)
    lo = lo.date() if isinstance(lo, dt.datetime) else lo
    hi = hi.date() if isinstance(hi, dt.datetime) else hi
    return lo <= _BLACK_FRIDAY <= hi


def _safe_json(s: str) -> Any:
    try:
        start, end = s.find("{"), s.rfind("}")
        return json.loads(s[start : end + 1]) if start >= 0 else None
    except (json.JSONDecodeError, ValueError):
        return None
