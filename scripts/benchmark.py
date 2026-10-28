"""Phase 6 — latency benchmark for the dashboard (and, optionally, the agent).

Runs the representative dashboard query shapes against one or more schemas and
reports cold (database) vs warm (TTL-cache hit) latency, then writes the numbers
into ``docs/SCALING.md``. By default it benchmarks ``mart`` (the real reporting
layer); pass several schemas to ``--schemas`` to compare sizes.

Usage (from repo root):
    python -m scripts.benchmark                         # mart
    python -m scripts.benchmark --write                 # mart + update SCALING.md
    python -m scripts.benchmark --schemas mart,other    # compare two schemas
    python -m scripts.benchmark --agent "top 5 categories by revenue"  # time the agent

The query shapes mirror services/charts.py; they are run with the same read-only,
statement-timeout discipline as the live app.
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import get_settings  # noqa: E402
from db.session import read_only_session  # noqa: E402
from services.cache import TTLCache  # noqa: E402

# Date window = the dashboard default (DASHBOARD_SPEC.md §6).
PARAMS = {"date_from": "2017-01-01", "date_to": "2018-08-31"}

# name -> SQL template with a {s} schema placeholder. Shapes mirror services/charts.py.
QUERIES: dict[str, str] = {
    "kpis": """
        SELECT COALESCE(SUM(items_gmv),0) AS gmv, COUNT(*) AS orders,
               AVG(review_score) AS avg_review
        FROM {s}.order_facts
        WHERE purchase_date BETWEEN :date_from AND :date_to
          AND status NOT IN ('canceled','unavailable')
    """,
    "trend_month": """
        SELECT purchase_month AS period, SUM(items_gmv) AS gmv, COUNT(*) AS orders
        FROM {s}.order_facts
        WHERE purchase_date BETWEEN :date_from AND :date_to
          AND status NOT IN ('canceled','unavailable')
        GROUP BY 1 ORDER BY 1
    """,
    "top_categories": """
        SELECT category, SUM(gmv) AS gmv, SUM(orders) AS orders
        FROM {s}.daily_sales
        WHERE date BETWEEN :date_from AND :date_to
          AND status NOT IN ('canceled','unavailable')
        GROUP BY category ORDER BY gmv DESC LIMIT 10
    """,
    "revenue_by_state": """
        SELECT customer_state AS state, SUM(items_gmv) AS gmv, COUNT(*) AS orders
        FROM {s}.order_facts
        WHERE purchase_date BETWEEN :date_from AND :date_to
          AND status NOT IN ('canceled','unavailable')
        GROUP BY 1 ORDER BY gmv DESC LIMIT 27
    """,
    "late_by_state": """
        SELECT customer_state AS state,
               AVG(CASE WHEN is_late THEN 1.0 ELSE 0.0 END) AS late_pct, COUNT(*) AS orders
        FROM {s}.order_facts
        WHERE purchase_date BETWEEN :date_from AND :date_to
          AND status NOT IN ('canceled','unavailable') AND is_late IS NOT NULL
        GROUP BY 1 HAVING COUNT(*) >= 30 ORDER BY late_pct DESC LIMIT 27
    """,
}


def _median_ms(fn, iterations: int) -> float:
    samples = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000)
    return round(statistics.median(samples), 1)


def _row_counts(schema: str) -> dict[str, int]:
    out = {}
    with read_only_session() as s:
        for t in ("order_facts", "order_item_facts", "daily_sales"):
            try:
                out[t] = int(s.execute(text(f"SELECT COUNT(*) FROM {schema}.{t}")).scalar() or 0)
            except Exception:  # noqa: BLE001 - schema/table may not exist
                out[t] = 0
    return out


def bench_schema(schema: str, iterations: int) -> dict[str, dict[str, float]]:
    """Return {query_name: {cold_ms, warm_ms}} for one schema."""
    timeout = int(get_settings().sql_statement_timeout_ms)
    cache = TTLCache()
    results: dict[str, dict[str, float]] = {}

    for name, tmpl in QUERIES.items():
        sql = tmpl.format(s=schema)

        def run_db() -> list:
            with read_only_session() as s:
                s.execute(text(f"SET statement_timeout = {timeout}"))
                return s.execute(text(sql), PARAMS).mappings().all()

        # Warm the DB-side plan cache with one untimed run, then measure cold DB latency.
        run_db()
        cold = _median_ms(run_db, iterations)
        # Warm = TTL-cache hit (prime once, then every call is an in-process read).
        cache.cached(sql, PARAMS, run_db)
        warm = _median_ms(lambda: cache.cached(sql, PARAMS, run_db), iterations)
        results[name] = {"cold_ms": cold, "warm_ms": warm}
    return results


def time_agent(question: str) -> dict:
    from agent.graph import ask
    from agent.llm import get_llm

    t0 = time.perf_counter()
    state = ask(question, thread_id="bench")
    return {
        "question": question,
        "seconds": round(time.perf_counter() - t0, 2),
        "llm": get_llm().name,
        "rows": state.get("row_count", 0),
    }


def render_markdown(all_results: dict[str, dict], counts: dict[str, dict], agent: dict | None) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    schemas = list(all_results)
    lines = [
        "# Scaling & Benchmarks",
        "",
        "> Auto-generated by `python -m scripts.benchmark --write`. "
        f"Last run: **{now}**.",
        "",
        "Latency of the representative dashboard query shapes (they mirror "
        "`services/charts.py`), measured read-only with the production "
        "`statement_timeout`. **Cold** = executed on CockroachDB; **warm** = "
        "served from the in-process TTL cache (`hash(sql+params)`).",
        "",
        "## Dataset sizes",
        "",
        "| schema | order_facts | order_item_facts | daily_sales |",
        "|---|--:|--:|--:|",
    ]
    for s in schemas:
        c = counts.get(s, {})
        lines.append(f"| `{s}` | {c.get('order_facts',0):,} | "
                     f"{c.get('order_item_facts',0):,} | {c.get('daily_sales',0):,} |")
    lines += ["", "## Query latency (median ms)", ""]
    header = "| query | " + " | ".join(f"{s} cold | {s} warm" for s in schemas) + " |"
    sep = "|---|" + "".join("--:|--:|" for _ in schemas)
    lines += [header, sep]
    for q in QUERIES:
        cells = []
        for s in schemas:
            r = all_results[s][q]
            cells.append(f"{r['cold_ms']} | {r['warm_ms']}")
        lines.append(f"| `{q}` | " + " | ".join(cells) + " |")
    if len(schemas) == 2:
        lines += ["", "## Cold-latency ratio (bench ÷ mart)", ""]
        a, b = schemas
        base = counts.get(a, {}).get("order_facts", 0) or 1
        grown = counts.get(b, {}).get("order_facts", 0) or 1
        lines.append(f"Data grew **{grown / base:.1f}x** ({base:,} -> {grown:,} orders).")
        lines += ["", "| query | latency ratio |", "|---|--:|"]
        for q in QUERIES:
            ca, cb = all_results[a][q]["cold_ms"], all_results[b][q]["cold_ms"]
            lines.append(f"| `{q}` | {cb / ca:.2f}x |" if ca else f"| `{q}` | n/a |")
    if agent:
        lines += ["", "## Agent latency (one NL question, end-to-end)", "",
                  f"- Question: _{agent['question']}_",
                  f"- LLM: `{agent['llm']}`",
                  f"- Rows returned: {agent['rows']}",
                  f"- Wall-clock: **{agent['seconds']}s** "
                  "(dominated by the LLM NL→SQL + insight calls, not the query)."]
    lines += [
        "", "## Reading these numbers",
        "",
        "- **Pre-aggregation is why it scales.** Every dashboard query hits a "
        "pre-aggregated, indexed `mart.*` table, so cost grows with the number of "
        "*groups* (months, states, categories), not raw orders. 10x the orders is "
        "far less than 10x the latency.",
        "- **The cache flattens repeat load.** A warm hit is ~0 ms, so dashboards "
        "with many viewers on the same filters pay the DB cost once per TTL.",
        "- **Where it would break first at true scale:** a single-process TTL "
        "cache and the in-memory report store don't share across workers — the "
        "documented next step is Redis / object storage behind the same interface "
        "(see ARCHITECTURE_REVIEW.md §3).",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Benchmark dashboard (and agent) latency.")
    ap.add_argument("--schemas", default="mart", help="comma-separated schemas, e.g. mart,bench")
    ap.add_argument("--iterations", type=int, default=5, help="samples per query (median reported)")
    ap.add_argument("--agent", nargs="?", const="top 5 categories by revenue",
                    help="also time one NL question through the agent")
    ap.add_argument("--write", action="store_true", help="write docs/SCALING.md")
    args = ap.parse_args()

    schemas = [s.strip() for s in args.schemas.split(",") if s.strip()]
    counts = {s: _row_counts(s) for s in schemas}
    all_results: dict[str, dict] = {}
    for s in schemas:
        if counts[s]["order_facts"] == 0:
            print(f"! schema '{s}' has no order_facts — skipping")
            continue
        print(f"benchmarking schema '{s}' ({counts[s]['order_facts']:,} orders)…")
        all_results[s] = bench_schema(s, args.iterations)

    # Console table.
    for s, res in all_results.items():
        print(f"\n== {s} ==")
        for q, r in res.items():
            print(f"  {q:18s} cold {r['cold_ms']:>8.1f} ms   warm {r['warm_ms']:>7.1f} ms")

    agent = None
    if args.agent:
        print("\ntiming agent…")
        agent = time_agent(args.agent)
        print(f"  agent: {agent['seconds']}s via {agent['llm']} ({agent['rows']} rows)")

    if args.write and all_results:
        out = ROOT / "docs" / "SCALING.md"
        out.write_text(render_markdown(all_results, counts, agent), encoding="utf-8")
        print(f"\n[ok] wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
