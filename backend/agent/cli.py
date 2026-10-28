"""Command-line harness for the agent.

    python -m agent.cli                      # interactive REPL (keeps memory)
    python -m agent.cli "top 5 categories"   # one-shot

Shows the routed intent, the validated SQL, a preview of the aggregated rows,
and the insight — so the agent can be exercised before the chat UI exists.
"""
from __future__ import annotations

import sys
import uuid
from typing import Any

from agent.graph import get_agent
from agent.llm import get_llm


def _fmt_cell(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:,.2f}"
    return str(v)


def _print_table(rows: list[dict[str, Any]], limit: int = 12) -> None:
    if not rows:
        print("  (no rows)")
        return
    cols = list(rows[0].keys())
    widths = {c: min(max(len(c), *(len(_fmt_cell(r.get(c))) for r in rows[:limit])), 28) for c in cols}
    print("  " + " | ".join(c.ljust(widths[c]) for c in cols))
    print("  " + "-+-".join("-" * widths[c] for c in cols))
    for r in rows[:limit]:
        print("  " + " | ".join(_fmt_cell(r.get(c))[: widths[c]].ljust(widths[c]) for c in cols))
    if len(rows) > limit:
        print(f"  … {len(rows) - limit} more row(s)")


def run_once(agent, question: str, thread_id: str) -> None:
    state = agent.invoke({"question": question}, config={"configurable": {"thread_id": thread_id}})
    print(f"\n  intent : {state.get('intent')}")
    if state.get("sql"):
        print(f"  sql    : {state['sql']}")
    if state.get("chart_spec"):
        print(f"  chart  : {state['chart_spec']}")
    print(f"  rows   : {state.get('row_count', 0)}")
    _print_table(state.get("result") or [])
    print(f"\n  insight: {state.get('insight', '')}\n")


def main(argv: list[str]) -> int:
    agent = get_agent()
    print(f"Sales Intelligence agent — LLM: {get_llm().name}")

    if len(argv) > 1:
        run_once(agent, " ".join(argv[1:]), thread_id="oneshot")
        return 0

    thread_id = f"cli-{uuid.uuid4().hex[:8]}"
    print("Type a question (or 'exit'). Follow-ups share memory, e.g. 'now only for SP'.\n")
    while True:
        try:
            q = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not q:
            continue
        if q.lower() in ("exit", "quit", ":q"):
            return 0
        try:
            run_once(agent, q, thread_id)
        except Exception as exc:  # noqa: BLE001 - keep the REPL alive
            print(f"  error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
