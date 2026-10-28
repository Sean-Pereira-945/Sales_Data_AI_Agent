"""Report generation: plan sections → run deterministic queries → render charts
server-side → write narrative → assemble Markdown + PDF.

Reuses the Phase 1 chart queries and the Phase 3/4 analyzer + insight writer, so
a report is just the dashboard's building blocks composed into a document. The
LLM only ever sees aggregated facts (never raw rows). Charts are rendered with
matplotlib (Agg backend — no display, pure-python PDF), so there are no system
dependencies.
"""
from __future__ import annotations

import base64
import datetime as dt
import io
import textwrap
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure

from agent.llm import get_llm
from agent.nodes.analysis import summarize_rows
from agent.prompts import INSIGHT_SYSTEM, SUMMARY_SYSTEM
from api.filters import Filters
from services import charts

BLUE, AMBER, GREEN, RED, VIOLET = "#2563eb", "#f59e0b", "#10b981", "#dc2626", "#7c3aed"
A4 = (8.27, 11.69)


def _humanize(s: str) -> str:
    return s.replace("_", " ").strip().title()


# --------------------------------------------------------------------------- #
# Section catalog (reuses services/charts)
# --------------------------------------------------------------------------- #
@dataclass
class Section:
    id: str
    title: str
    fetch: Callable[[Filters], list[dict[str, Any]]]
    kind: str                 # line | bar | barh
    x: str
    y: str
    hint: str
    y_is_currency: bool = False


CATALOG: dict[str, Section] = {
    "trend": Section(
        "trend", "GMV (R$), monthly",
        lambda f: charts.trend(f, granularity="month")["data"],
        "line", "period", "gmv", "GMV (R$) over time", y_is_currency=True,
    ),
    "top_categories": Section(
        "top_categories", "Top categories by GMV (R$)",
        lambda f: charts.top_categories(f, top_n=10, metric="gmv")["data"],
        "barh", "category", "value", "top product categories by GMV", y_is_currency=True,
    ),
    "revenue_by_state": Section(
        "revenue_by_state", "Revenue by state (R$)",
        lambda f: charts.revenue_by_state(f, metric="gmv")["data"],
        "bar", "state", "gmv", "revenue by customer state", y_is_currency=True,
    ),
    "delay_vs_review": Section(
        "delay_vs_review", "Avg review score by delivery delay",
        lambda f: charts.delay_vs_review(f)["data"],
        "bar", "delay_bucket", "avg_review",
        "average review score by delivery-delay bucket (the headline relationship)",
    ),
    "late_by_state": Section(
        "late_by_state", "Late-delivery % by state",
        lambda f: charts.late_by_state(f, min_orders=30, sort="late_pct")["data"],
        "bar", "state", "late_pct", "late-delivery percentage by state",
    ),
    "review_distribution": Section(
        "review_distribution", "Review score distribution",
        lambda f: charts.review_distribution(f, view="distribution")["data"],
        "bar", "score", "reviews", "distribution of 1–5★ review scores",
    ),
    "seller_concentration": Section(
        "seller_concentration", "Seller concentration (Pareto)",
        lambda f: charts.seller_concentration(f, buckets=20)["data"],
        "line", "seller_pct", "cum_gmv_pct", "seller GMV concentration / platform risk",
    ),
}

_DEFAULT = ["trend", "top_categories", "revenue_by_state", "delay_vs_review"]
_KEYWORD_PLAN: list[tuple[tuple[str, ...], list[str]]] = [
    (("region", "state", "geograph", "location"), ["trend", "revenue_by_state", "late_by_state"]),
    (("deliver", "late", "logistic", "shipping", "delay"), ["delay_vs_review", "late_by_state", "trend"]),
    (("product", "categor", "catalog"), ["trend", "top_categories", "review_distribution"]),
    (("review", "satisf", "quality", "rating", "experience"), ["delay_vs_review", "review_distribution", "top_categories"]),
    (("seller", "merchant", "vendor"), ["seller_concentration", "top_categories", "revenue_by_state"]),
]


def plan_sections(topic: str) -> list[str]:
    """Rule-based section planner (deterministic). Picks sections by topic."""
    t = (topic or "").lower()
    chosen: list[str] = []
    for keys, ids in _KEYWORD_PLAN:
        if any(k in t for k in keys):
            chosen = ids
            break
    if not chosen:
        chosen = _DEFAULT
    # De-dupe, keep order, cap at 5.
    seen: set[str] = set()
    out = [s for s in chosen if not (s in seen or seen.add(s))]
    return out[:5]


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def _draw(ax, section: Section, rows: list[dict[str, Any]]) -> None:
    if not rows:
        ax.text(0.5, 0.5, "No data for these filters", ha="center", va="center", color="#64748b")
        ax.axis("off")
        return
    xs = [_humanize(str(r[section.x])) if section.x in ("category",) else str(r[section.x]) for r in rows]
    ys = [float(r.get(section.y) or 0) for r in rows]

    if section.kind == "line":
        ax.plot(xs, ys, color=BLUE, linewidth=2)
        ax.fill_between(range(len(xs)), ys, color=BLUE, alpha=0.08)
        step = max(1, len(xs) // 8)
        ax.set_xticks(range(0, len(xs), step))
        ax.set_xticklabels([xs[i] for i in range(0, len(xs), step)], rotation=45, ha="right", fontsize=7)
    elif section.kind == "barh":
        ax.barh(xs[::-1], ys[::-1], color=BLUE)
        ax.tick_params(axis="y", labelsize=7)
    else:  # bar
        colors = [RED if section.y == "late_pct" else BLUE for _ in xs]
        ax.bar(xs, ys, color=colors)
        ax.tick_params(axis="x", labelrotation=45, labelsize=7)

    ax.set_title(section.title, fontsize=11, fontweight="bold", loc="left")
    ax.grid(axis="y" if section.kind != "barh" else "x", alpha=0.25)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    if section.y_is_currency:
        ax.yaxis.set_major_formatter(lambda v, _p: f"R${v/1e6:.1f}M" if abs(v) >= 1e6 else f"R${v/1e3:.0f}k")


def _figure(section: Section, rows: list[dict[str, Any]]) -> Figure:
    fig, ax = plt.subplots(figsize=(7.5, 3.4), dpi=120)
    _draw(ax, section, rows)
    fig.tight_layout()
    return fig


def _png_b64(fig: Figure) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


# --------------------------------------------------------------------------- #
# Narrative (LLM, numbers-grounded)
# --------------------------------------------------------------------------- #
def _narrative(hint: str, facts: list[str]) -> str:
    user = f"Chart: {hint}.\nFACTS:\n" + "\n".join(facts)
    try:
        return get_llm().complete(INSIGHT_SYSTEM, user, purpose="insight", max_tokens=400) or facts[0]
    except Exception:  # noqa: BLE001
        return facts[0] if facts else "No data."


def _exec_summary(topic: str, built: list[tuple[Section, list, list[str]]]) -> str:
    blocks: list[str] = [f"Report topic: {topic}"]
    for sec, _rows, facts in built:
        blocks.append(f"\n{sec.hint}:")
        blocks.extend(facts)
    try:
        return get_llm().complete(SUMMARY_SYSTEM, "FACTS:\n" + "\n".join(blocks), purpose="summary", max_tokens=600)
    except Exception:  # noqa: BLE001
        return "Headline: summary unavailable.\n" + "\n".join(blocks[:6])


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #
@dataclass
class ReportResult:
    id: str
    title: str
    topic: str
    created_at: str
    section_titles: list[str]
    markdown: str
    pdf: bytes = field(repr=False, default=b"")


def _subtitle(f: Filters) -> str:
    return (f"Period {f.date_from} to {f.date_to}  ·  "
            f"states: {', '.join(f.states) or 'all'}  ·  "
            f"categories: {', '.join(f.categories) or 'all'}  ·  currency BRL (R$)")


def _markdown(title: str, f: Filters, summary: str,
              built: list[tuple[Section, list, list[str]]]) -> str:
    lines = [f"# {title}", "", f"_{_subtitle(f)}_", "",
             f"_Generated {dt.datetime.now().isoformat(timespec='seconds')}._", "",
             "## Executive summary", "", summary, ""]
    for sec, rows, narrative in built:
        lines += [f"## {sec.title}", "", narrative, ""]
        img = _png_b64(_figure(sec, rows))
        lines += [f"![{sec.title}](data:image/png;base64,{img})", ""]
    return "\n".join(lines)


def _wrap(text: str, width: int = 104) -> str:
    return "\n".join(textwrap.fill(ln, width) for ln in text.splitlines())


def _pdf(title: str, f: Filters, summary: str,
         built: list[tuple[Section, list, list[str]]]) -> bytes:
    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        cover = plt.figure(figsize=A4)
        cover.text(0.08, 0.92, title, fontsize=20, fontweight="bold")
        cover.text(0.08, 0.89, _subtitle(f), fontsize=8, color="#64748b")
        cover.text(0.08, 0.86, f"Generated {dt.datetime.now():%Y-%m-%d %H:%M}", fontsize=8, color="#64748b")
        cover.text(0.08, 0.80, "Executive summary", fontsize=13, fontweight="bold")
        cover.text(0.08, 0.77, _wrap(summary), fontsize=9, va="top", family="monospace")
        pdf.savefig(cover)
        plt.close(cover)

        for sec, rows, narrative in built:
            page = plt.figure(figsize=A4)
            ax = page.add_axes((0.10, 0.50, 0.82, 0.38))
            _draw(ax, sec, rows)
            page.text(0.08, 0.44, sec.title, fontsize=12, fontweight="bold")
            page.text(0.08, 0.41, _wrap(narrative), fontsize=9, va="top")
            pdf.savefig(page)
            plt.close(page)
    return buf.getvalue()


# In-process store of generated reports (dev single-process; keyed by id).
_REPORTS: dict[str, ReportResult] = {}
_MAX_REPORTS = 30


def build_report(topic: str, f: Filters) -> ReportResult:
    topic = (topic or "Sales overview").strip()
    built: list[tuple[Section, list, list[str]]] = []
    for sid in plan_sections(topic):
        sec = CATALOG[sid]
        rows = sec.fetch(f)
        facts = summarize_rows(rows).get("facts", [])
        built.append((sec, rows, _narrative(sec.hint, facts)))

    summary = _exec_summary(topic, built)
    title = f"Sales Intelligence Report — {topic[:60]}"
    rid = uuid.uuid4().hex[:12]
    result = ReportResult(
        id=rid, title=title, topic=topic,
        created_at=dt.datetime.now().isoformat(timespec="seconds"),
        section_titles=[s.title for s, _, _ in built],
        markdown=_markdown(title, f, summary, built),
        pdf=_pdf(title, f, summary, built),
    )
    _REPORTS[rid] = result
    if len(_REPORTS) > _MAX_REPORTS:
        del _REPORTS[next(iter(_REPORTS))]
    return result


def get_report(report_id: str) -> ReportResult | None:
    return _REPORTS.get(report_id)
