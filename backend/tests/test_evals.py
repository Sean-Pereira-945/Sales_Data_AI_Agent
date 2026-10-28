"""Phase 6: the eval set is well-formed and every ground-truth SQL is safe.

These run without an LLM — they check the dataset and that each ground-truth
query passes the same guard the agent's SQL must pass. The accuracy run itself
(`python -m evals.run_evals`) needs a live LLM to be meaningful.
"""
from __future__ import annotations

import json
from pathlib import Path

from guards.sql_validator import validate_sql

QUESTIONS = Path(__file__).resolve().parents[1] / "evals" / "questions.json"


def _questions() -> list[dict]:
    return json.loads(QUESTIONS.read_text(encoding="utf-8"))["questions"]


def test_question_set_shape():
    qs = _questions()
    assert len(qs) == 20
    ids = [q["id"] for q in qs]
    assert len(set(ids)) == len(ids)  # unique ids
    for q in qs:
        assert q["question"].strip() and q["sql"].strip()


def test_ground_truth_sql_passes_guard():
    # Every ground-truth query must be a safe, read-only, whitelisted SELECT —
    # the same bar the agent's generated SQL is held to.
    for q in _questions():
        result = validate_sql(q["sql"])
        assert result.ok, f"{q['id']}: {result.reason}"
