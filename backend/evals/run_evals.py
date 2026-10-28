"""Phase 6 — agent evaluation harness.

For each question in ``questions.json`` it runs the question through the real
LangGraph agent, then compares the agent's answer to a ground-truth SQL result by
**execution** (run both, compare the result sets) rather than by string-matching
the SQL — so a correct answer phrased differently still passes.

Comparison is order-insensitive and tolerant of column aliasing/ordering: each
row is normalized to a sorted tuple of rounded values, and the two multisets of
rows are compared. Floats are rounded to 2 significant-ish decimals and scaled
counts are compared with a small relative tolerance.

Run (from backend/):
    python -m evals.run_evals
    python -m evals.run_evals --verbose

Exit code is 0 unless --strict is passed and accuracy < the threshold. The score
only means something with a working LLM key; on the offline stub it measures the
stub, not the agent (the printed LLM name tells you which).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import text

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # backend/ on path

from agent.graph import ask
from agent.llm import get_llm
from db.session import read_only_session
from guards.sql_validator import validate_sql

REL_TOL = 0.02  # 2% tolerance for aggregate magnitudes (FP / ordering noise)


def _run_sql(sql: str) -> list[dict]:
    with read_only_session() as s:
        s.execute(text("SET statement_timeout = 15000"))
        return [dict(r) for r in s.execute(text(sql)).mappings()]


def _norm_value(v: object) -> object:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return round(float(v), 2)
    return str(v).strip()


def _norm_rows(rows: list[dict]) -> list[tuple]:
    """Order-insensitive, alias-insensitive normal form for a result set."""
    return sorted(tuple(sorted(str(_norm_value(v)) for v in r.values())) for r in rows)


def _close(a: float, b: float) -> bool:
    if a == b:
        return True
    denom = max(abs(a), abs(b), 1.0)
    return abs(a - b) / denom <= REL_TOL


def _equivalent(expected: list[dict], got: list[dict]) -> bool:
    if len(expected) != len(got):
        return False
    # Single-cell numeric answers: compare with relative tolerance.
    if len(expected) == 1 and len(expected[0]) == 1 and len(got) >= 1:
        ev = next(iter(expected[0].values()))
        # find a numeric value in the agent's first row that matches within tolerance
        for gv in got[0].values():
            numeric = (isinstance(ev, (int, float)) and isinstance(gv, (int, float))
                       and not isinstance(ev, bool) and not isinstance(gv, bool))
            if numeric and _close(float(ev), float(gv)):
                return True
    return _norm_rows(expected) == _norm_rows(got)


def evaluate(verbose: bool = False) -> float:
    data = json.loads((HERE / "questions.json").read_text(encoding="utf-8"))
    questions = data["questions"]
    llm_name = get_llm().name
    print(f"LLM: {llm_name}\nQuestions: {len(questions)}\n" + "-" * 64)

    passed = 0
    for q in questions:
        qid, question, truth_sql = q["id"], q["question"], q["sql"]
        try:
            expected = _run_sql(truth_sql)
        except Exception as exc:  # noqa: BLE001
            print(f"[SKIP] {qid}: ground-truth SQL failed ({type(exc).__name__})")
            continue

        try:
            state = ask(question, thread_id=f"eval-{qid}")
            agent_sql = state.get("sql") or ""
            got = state.get("result") or []
            # Defense check: the agent's SQL must have passed the guard.
            guard_ok = bool(agent_sql) and validate_sql(agent_sql).ok
            ok = guard_ok and _equivalent(expected, got)
        except Exception as exc:  # noqa: BLE001
            ok, agent_sql, got = False, f"<error: {type(exc).__name__}>", []

        passed += ok
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {qid:22s} {question}")
        if verbose and not ok:
            print(f"        expected {len(expected)} row(s): {expected[:2]}")
            print(f"        agent    {len(got)} row(s): {got[:2]}")
            print(f"        agent SQL: {agent_sql[:160]}")

    accuracy = passed / len(questions) if questions else 0.0
    print("-" * 64)
    print(f"Accuracy: {passed}/{len(questions)} = {accuracy:.0%}")
    if get_llm().name.startswith("stub"):
        print("NOTE: running on the offline stub — this scores the fallback, not the "
              "real agent. Set a working LLM key for a meaningful number.")
    return accuracy


def main() -> None:
    ap = argparse.ArgumentParser(description="Evaluate the agent against ground-truth SQL.")
    ap.add_argument("--verbose", action="store_true", help="show diffs for failures")
    ap.add_argument("--strict", action="store_true", help="exit non-zero if below --threshold")
    ap.add_argument("--threshold", type=float, default=0.8, help="pass threshold for --strict")
    args = ap.parse_args()
    accuracy = evaluate(verbose=args.verbose)
    if args.strict and accuracy < args.threshold:
        raise SystemExit(f"accuracy {accuracy:.0%} below threshold {args.threshold:.0%}")


if __name__ == "__main__":
    main()
