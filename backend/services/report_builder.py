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
import json
import logging
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
from sqlalchemy import text

from agent.llm import get_llm
from agent.nodes.analysis import summarize_rows
from agent.prompts import (
    CHART_SPEC_SYSTEM,
    INSIGHT_SYSTEM,
    REPORT_OUTLINE_SYSTEM,
    REPORT_PLAN_SYSTEM,
    SQL_SYSTEM,
    SUMMARY_SYSTEM,
)
from api.filters import Filters
from db.session import read_only_session
from guards.sql_validator import validate_sql
from services import charts

BLUE, AMBER, GREEN, RED, VIOLET = "#2563eb", "#f59e0b", "#10b981", "#dc2626", "#7c3aed"
A4 = (8.27, 11.69)
logger = logging.getLogger(__name__)


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


@dataclass
class DynamicSection:
    """A topic-specific chart built from one guarded aggregated query."""

    id: str
    title: str
    hint: str
    x: str
    y: str
    kind: str
    y_is_currency: bool = False


@dataclass
class SectionSpec:
    """One planned section of a report: either a catalog chart or a custom one.

    The planner (``plan_report``) decides the mix dynamically from the user's
    request; ``build_report`` then materializes each spec into a BuiltSection.
    """

    source: str                       # "catalog" | "custom"
    catalog_id: str | None = None     # set when source == "catalog"
    title: str | None = None          # set when source == "custom"
    question: str | None = None       # set when source == "custom"


Row = dict[str, Any]
BuiltSection = tuple[Section | DynamicSection, list[Row], str]

# A report has 3–6 sections; keep the number of LLM-written custom queries
# bounded so generation latency stays predictable.
_MAX_SECTIONS = 6
_MAX_CUSTOM = 3


CATALOG: dict[str, Section] = {
    "trend": Section(
        "trend", "GMV (R$), monthly",
        lambda f: charts.trend(f, granularity="month")["data"],
        "line", "period", "gmv", "GMV (R$) over time", y_is_currency=True,
    ),
    "trend_aov": Section(
        "trend_aov", "Average order value over time",
        lambda f: charts.trend(f, granularity="month")["data"],
        "line", "period", "aov", "average order value (AOV) over time",
        y_is_currency=True,
    ),
    "top_categories": Section(
        "top_categories", "Top categories by GMV (R$)",
        lambda f: charts.top_categories(f, top_n=10, metric="gmv")["data"],
        "barh", "category", "value", "top product categories by GMV", y_is_currency=True,
    ),
    "category_aov": Section(
        "category_aov", "Average order value by category",
        lambda f: charts.top_categories(f, top_n=10, metric="aov")["data"],
        "barh", "category", "value", "average order value (AOV) by product category",
        y_is_currency=True,
    ),
    "revenue_by_state": Section(
        "revenue_by_state", "Revenue by state (R$)",
        lambda f: charts.revenue_by_state(f, metric="gmv")["data"],
        "bar", "state", "gmv", "revenue by customer state", y_is_currency=True,
    ),
    "aov_by_state": Section(
        "aov_by_state", "Average order value by state",
        lambda f: charts.revenue_by_state(f, metric="aov")["data"],
        "bar", "state", "value", "average order value (AOV) by customer state",
        y_is_currency=True,
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
    (("aov", "average order value", "order value", "basket size"),
     ["category_aov", "trend_aov"]),
    (("region", "state", "geograph", "location"), ["trend", "revenue_by_state", "late_by_state"]),
    (("deliver", "late", "logistic", "shipping", "delay"), ["delay_vs_review", "late_by_state", "trend"]),
    (("product", "categor", "catalog"), ["top_categories"]),
    (("review", "satisf", "quality", "rating", "experience"), ["delay_vs_review", "review_distribution", "top_categories"]),
    (("seller", "merchant", "vendor"), ["seller_concentration", "top_categories", "revenue_by_state"]),
]


def plan_sections(topic: str) -> list[str]:
    """Choose relevant approved sections, using the LLM with a safe fallback."""
    t = (topic or "").lower()
    chosen: list[str] = []
    matched_topic = False
    wants_aov = any(k in t for k in ("aov", "average order value", "order value", "basket size"))
    wants_state = any(k in t for k in ("state", "states", "sttes", "region", "regional", "geograph", "location"))
    wants_category = any(k in t for k in ("categor", "product", "catalog"))

    if wants_aov and wants_state:
        chosen = ["aov_by_state"]
        matched_topic = True
    elif wants_aov and wants_category:
        chosen = ["category_aov", "trend_aov"]
        matched_topic = True
    else:
        for keys, ids in _KEYWORD_PLAN:
            if any(k in t for k in keys):
                chosen = ids
                matched_topic = True
                break
    if not chosen:
        chosen = _DEFAULT

    catalog = "\n".join(f"- {sid}: {section.hint}" for sid, section in CATALOG.items())
    prompt = f"User topic: {topic}\n\nApproved catalog:\n{catalog}"
    try:
        raw = get_llm().complete(REPORT_PLAN_SYSTEM, prompt, purpose="report_plan", max_tokens=120)
        planned = json.loads(raw)
        if isinstance(planned, list):
            dynamic = [sid for sid in planned if isinstance(sid, str) and sid in CATALOG]
            if matched_topic:
                dynamic = [sid for sid in dynamic if sid in chosen]
            if 1 <= len(dynamic) <= 5:
                chosen = dynamic
    except (json.JSONDecodeError, TypeError, ValueError):
        logger.warning("Report planner returned invalid section IDs; using topic fallback")
    except Exception as exc:  # noqa: BLE001 - report generation must remain available
        logger.warning("Dynamic report planning failed (%s); using topic fallback", type(exc).__name__)

    # De-dupe, keep order, cap at 5.
    seen: set[str] = set()
    out = [s for s in chosen if not (s in seen or seen.add(s))]
    return out[:5]


def _strip_sql_fences(sql: str) -> str:
    if "```" in sql:
        sql = sql.replace("```sql", "").replace("```SQL", "").replace("```", "")
    return sql.strip().rstrip(";").strip()


def _loads_json(raw: str) -> Any:
    """Parse JSON that may be wrapped in ``` fences or prose. Raises on failure."""
    text_value = (raw or "").strip()
    if "```" in text_value:
        text_value = text_value.replace("```json", "").replace("```JSON", "").replace("```", "").strip()
    # Tolerate a leading sentence before the JSON payload: if it doesn't already
    # start with a JSON opener, slice from the first opener to its matching last
    # closer (picking [] vs {} by whichever opener appears first).
    if text_value and text_value[0] not in "[{":
        openers = [i for i in (text_value.find("["), text_value.find("{")) if i != -1]
        if openers:
            start = min(openers)
            closer = "]" if text_value[start] == "[" else "}"
            end = text_value.rfind(closer)
            if start < end:
                text_value = text_value[start : end + 1]
    return json.loads(text_value)


def _pick_axes(
    columns: list[str], rows: list[Row], spec: dict[str, Any]
) -> tuple[str, str, str]:
    """Resolve (x, y, kind) from an optional chart spec, guarded against bad picks."""
    numeric = [c for c in columns if any(isinstance(r.get(c), (int, float)) for r in rows)]
    labels = [c for c in columns if c not in numeric]
    x_value, y_value = spec.get("x"), spec.get("y")
    x = x_value if isinstance(x_value, str) else None
    y = y_value if isinstance(y_value, str) else None
    if x not in columns or x in numeric:
        x = labels[0] if labels else columns[0]
    if y not in columns or y not in numeric:
        y = numeric[0] if numeric else columns[-1]
    kind_value = spec.get("type")
    kind = kind_value if isinstance(kind_value, str) else "bar"
    if kind not in {"line", "bar", "barh"}:
        kind = "line" if x in {"date", "month", "period", "purchase_month"} else "bar"
    return x, y, kind


def _build_custom_section(
    title: str, question: str, f: Filters, idx: int
) -> tuple[DynamicSection, list[Row]] | None:
    """Turn one planned custom section into (DynamicSection, rows).

    The LLM writes the aggregated SQL for ``question``; it passes through the
    same guard as every agent query, runs read-only with a statement timeout,
    and only the small aggregated result is ever seen again. Returns None on any
    rejection/empty result so the caller can simply skip the section.
    """
    client = get_llm()
    sql_prompt = (
        f"Question: {question}\n\n"
        f"Current filters: {f.date_from} to {f.date_to}; "
        f"states={f.states or 'all'}; categories={f.categories or 'all'}.\n"
        "Return an aggregated query with one descriptive dimension column and "
        "one or more numeric measures suitable for a chart. Do not return raw rows."
    )
    validation = validate_sql(_strip_sql_fences(
        client.complete(SQL_SYSTEM, sql_prompt, purpose="sql", max_tokens=700)
    ))
    if not validation.ok:
        logger.warning("Custom report SQL rejected (%s): %s", title, validation.reason)
        return None

    try:
        with read_only_session() as session:
            session.execute(text("SET statement_timeout = 5000"))
            rows: list[Row] = [
                {str(key): value for key, value in row.items()}
                for row in session.execute(text(validation.sql)).mappings()
            ]
    except Exception as exc:  # noqa: BLE001 - skip this section, keep the report
        logger.warning("Custom report query failed (%s): %s", title, type(exc).__name__)
        return None
    if not rows:
        return None

    columns = list(rows[0])
    spec_prompt = (
        f"Question: {question}\nAggregated result columns: {columns}\n"
        "Choose the best chart for this result."
    )
    try:
        decoded = _loads_json(
            client.complete(CHART_SPEC_SYSTEM, spec_prompt, purpose="chart_spec", max_tokens=160)
        )
        spec: dict[str, Any] = decoded if isinstance(decoded, dict) else {}
    except (json.JSONDecodeError, TypeError, ValueError):
        spec = {}
    x, y, kind = _pick_axes(columns, rows, spec)
    clean_title = (title or f"{_humanize(y)} by {_humanize(x)}").strip()[:80]
    section = DynamicSection(
        id=f"custom-{idx}",
        title=clean_title,
        hint=f"{clean_title} — {question}",
        x=x,
        y=y,
        kind=kind,
        y_is_currency=any(
            token in y.lower() for token in ("gmv", "aov", "value", "revenue", "price", "freight")
        ),
    )
    return section, rows


def plan_report(topic: str, f: Filters) -> list[SectionSpec]:
    """Plan the report's sections dynamically from the user's request.

    With a live LLM, the model outlines a mix of reliable catalog charts and
    topic-specific custom charts (see REPORT_OUTLINE_SYSTEM). When the LLM is
    unavailable, returns an empty/failed outline, or proposes nothing usable, we
    fall back to the deterministic keyword plan so a report is always produced.
    """
    fallback = [SectionSpec("catalog", catalog_id=sid) for sid in plan_sections(topic)]

    client = get_llm()
    if client.name.startswith("stub"):
        return fallback

    catalog_desc = "\n".join(f"- {sid}: {section.hint}" for sid, section in CATALOG.items())
    prompt = (
        f"User request: {topic}\n\n"
        f"Filters in effect: {f.date_from} to {f.date_to}; "
        f"states={f.states or 'all'}; categories={f.categories or 'all'}.\n\n"
        f"Approved catalog:\n{catalog_desc}"
    )
    try:
        items = _loads_json(
            client.complete(REPORT_OUTLINE_SYSTEM, prompt, purpose="report_outline", max_tokens=500)
        )
    except (json.JSONDecodeError, TypeError, ValueError):
        logger.warning("Report outline was not valid JSON; using keyword plan")
        return fallback
    except Exception as exc:  # noqa: BLE001 - report generation must remain available
        logger.warning("Report outline planning failed (%s); using keyword plan", type(exc).__name__)
        return fallback
    if not isinstance(items, list):
        return fallback

    specs: list[SectionSpec] = []
    custom_count = 0
    seen: set[tuple[str, str]] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        source = item.get("source")
        if source == "catalog":
            cid = item.get("id")
            if isinstance(cid, str) and cid in CATALOG and ("catalog", cid) not in seen:
                specs.append(SectionSpec("catalog", catalog_id=cid))
                seen.add(("catalog", cid))
        elif source == "custom" and custom_count < _MAX_CUSTOM:
            title, question = item.get("title"), item.get("question")
            if (
                isinstance(title, str)
                and isinstance(question, str)
                and question.strip()
                and ("custom", question.strip()) not in seen
            ):
                specs.append(SectionSpec("custom", title=title.strip(), question=question.strip()))
                seen.add(("custom", question.strip()))
                custom_count += 1
        if len(specs) >= _MAX_SECTIONS:
            break

    return specs or fallback


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def _draw(ax, section: Section | DynamicSection, rows: list[dict[str, Any]]) -> None:
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
        ax.yaxis.set_major_formatter(lambda v, _: f"R${v/1e6:.1f}M" if abs(v) >= 1e6 else f"R${v/1e3:.0f}k")


def _figure(section: Section | DynamicSection, rows: list[dict[str, Any]]) -> Figure:
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


def _exec_summary(topic: str, built: list[BuiltSection]) -> str:
    blocks: list[str] = [f"Report topic: {topic}"]
    for sec, _, facts in built:
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


def _summary_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _markdown(title: str, f: Filters, summary: str,
              built: list[BuiltSection]) -> str:
    generated = dt.datetime.now().isoformat(timespec="seconds")
    lines = [
        "# Sales Intelligence Report",
        "",
        f"## {title.removeprefix('Sales Intelligence Report — ')}",
        "",
        f"> **Generated:** {generated}  ",
        f"> **Scope:** {_subtitle(f)}",
        "",
        "## Contents",
        "",
    ]
    lines.extend(f"{index}. [{sec.title}](#{sec.id.replace('_', '-')})"
                 for index, (sec, _, _) in enumerate(built, start=1))
    lines += ["", "## Executive summary", "", summary, ""]
    for sec, rows, narrative in built:
        lines += [f'<a id="{sec.id.replace("_", "-")}"></a>', f"## {sec.title}", "",
                  narrative, ""]
        img = _png_b64(_figure(sec, rows))
        lines += [f"![{sec.title}](data:image/png;base64,{img})", ""]
    lines += ["---", "", "_All figures are calculated from the selected filters and aggregated reporting data._", ""]
    return "\n".join(lines)


def _pdf_text_block(page: Figure, text: str, x: float, y: float,
                    width: int = 92, line_height: float = 0.022) -> float:
    current_y = y
    for line in _summary_lines(text):
        wrapped = textwrap.wrap(line, width=width) or [""]
        for part in wrapped:
            page.text(x, current_y, part, fontsize=9, va="top")
            current_y -= line_height
        current_y -= line_height * 0.35
    return current_y


def _pdf(title: str, f: Filters, summary: str,
         built: list[BuiltSection]) -> bytes:
    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        cover = plt.figure(figsize=A4)
        cover.text(0.08, 0.93, "SALES INTELLIGENCE", fontsize=9, color=BLUE, fontweight="bold")
        cover.text(0.08, 0.88, title.removeprefix("Sales Intelligence Report — "),
                   fontsize=20, fontweight="bold")
        cover.text(0.08, 0.84, "Executive report", fontsize=10, color="#64748b")
        cover.text(0.08, 0.80, _subtitle(f), fontsize=8, color="#64748b")
        cover.text(0.08, 0.77, f"Generated {dt.datetime.now():%Y-%m-%d %H:%M}",
                   fontsize=8, color="#64748b")
        cover.text(0.08, 0.70, "Executive summary", fontsize=13, fontweight="bold")
        _pdf_text_block(cover, summary, 0.08, 0.66, width=92)
        cover.text(0.08, 0.08, f"{len(built)} analytical sections · BRL (R$)",
                   fontsize=8, color="#64748b")
        pdf.savefig(cover)
        plt.close(cover)

        total_pages = len(built) + 1
        for page_number, (sec, rows, narrative) in enumerate(built, start=2):
            page = plt.figure(figsize=A4)
            page.text(0.08, 0.94, f"{page_number - 1:02d}", fontsize=9, color=BLUE, fontweight="bold")
            page.text(0.15, 0.94, sec.title, fontsize=13, fontweight="bold")
            page.text(0.08, 0.90, sec.hint, fontsize=8, color="#64748b")
            ax = page.add_axes((0.10, 0.50, 0.82, 0.34))
            _draw(ax, sec, rows)
            page.text(0.08, 0.43, "Key takeaway", fontsize=10, fontweight="bold")
            _pdf_text_block(page, narrative, 0.08, 0.40, width=98, line_height=0.021)
            page.text(0.08, 0.08, f"Sales Intelligence Report · {page_number}/{total_pages}",
                      fontsize=8, color="#64748b")
            pdf.savefig(page)
            plt.close(page)
    return buf.getvalue()


# In-process store of generated reports (dev single-process; keyed by id).
_REPORTS: dict[str, ReportResult] = {}
_MAX_REPORTS = 30


def _facts_for(rows: list[Row]) -> list[str]:
    raw = summarize_rows(rows).get("facts", [])
    return [fact for fact in raw if isinstance(fact, str)] if isinstance(raw, list) else []


def _build_from_catalog(sid: str, f: Filters) -> BuiltSection:
    sec = CATALOG[sid]
    rows = sec.fetch(f)
    return sec, rows, _narrative(sec.hint, _facts_for(rows))


def build_report(topic: str, f: Filters) -> ReportResult:
    topic = (topic or "Sales overview").strip()
    built: list[BuiltSection] = []
    custom_idx = 0
    for spec in plan_report(topic, f):
        if spec.source == "catalog" and spec.catalog_id in CATALOG:
            built.append(_build_from_catalog(spec.catalog_id, f))
        elif spec.source == "custom" and spec.question:
            custom_idx += 1
            result = _build_custom_section(spec.title or "", spec.question, f, custom_idx)
            if result is None:
                continue  # rejected/empty custom query — skip, keep the report
            sec, rows = result
            built.append((sec, rows, _narrative(sec.hint, _facts_for(rows))))

    # If every planned section dropped out (e.g. all custom queries failed),
    # guarantee a usable report from the deterministic keyword plan.
    if not built:
        built = [_build_from_catalog(sid, f) for sid in plan_sections(topic)]

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
