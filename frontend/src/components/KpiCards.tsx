import { useKpis } from "../api/hooks";
import type { KpiCard } from "../api/types";
import { fmtBRL, fmtDelta, fmtInt, fmtPct, fmtStars } from "../lib/format";
import { Skeleton } from "./ui";

function formatValue(card: KpiCard): string {
  if (card.value === null) return "—";
  switch (card.unit) {
    case "BRL":
      return fmtBRL(card.value);
    case "%":
      return fmtPct(card.value);
    case "stars":
      return fmtStars(card.value);
    default:
      return fmtInt(card.value);
  }
}

export function KpiCards() {
  const q = useKpis();

  if (q.isPending) {
    return (
      <div className="kpi-row">
        {Array.from({ length: 6 }).map((_, i) => (
          <div className="kpi" key={i}>
            <Skeleton height={64} />
          </div>
        ))}
      </div>
    );
  }
  if (q.isError || !q.data) {
    return <div className="kpi-row"><div className="error-box">Couldn’t load KPIs.</div></div>;
  }

  const { cards, comparison_label } = q.data;

  return (
    <div className="kpi-row">
      {cards.map((card) => {
        const up = card.delta_pct !== null && card.delta_pct >= 0;
        const positiveIsGood = card.key !== "aov" ? true : true; // all six: higher is better
        const good = card.delta_pct === null ? null : up === positiveIsGood;
        return (
          <div className="kpi" key={card.key}>
            <div className="kpi-label">{card.label}</div>
            <div className="kpi-value">{formatValue(card)}</div>
            <div className="kpi-delta">
              {card.delta_pct === null ? (
                <span className="delta-muted">no prior period</span>
              ) : (
                <span className={good ? "delta-up" : "delta-down"}>
                  {up ? "▲" : "▼"} {fmtDelta(card.delta_pct)}
                </span>
              )}
            </div>
          </div>
        );
      })}
      <div className="kpi-compare">vs {comparison_label ?? "—"}</div>
    </div>
  );
}
