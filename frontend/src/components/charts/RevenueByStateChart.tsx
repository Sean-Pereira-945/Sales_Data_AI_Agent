import { useState } from "react";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useRevenueByState } from "../../api/hooks";
import type { StateRow } from "../../api/types";
import { SERIES } from "../../lib/colors";
import { fmtBRLCompact, fmtInt, fmtPct } from "../../lib/format";
import { ChartCard } from "../ChartCard";
import { CardControls, Segmented } from "../ui";

type Metric = "gmv" | "orders" | "aov" | "freight_pct";

const UNIT: Record<Metric, string> = {
  gmv: "GMV (R$)",
  orders: "Orders",
  aov: "AOV (R$)",
  freight_pct: "Freight % of GMV",
};

export function RevenueByStateChart() {
  const [metric, setMetric] = useState<Metric>("gmv");
  const q = useRevenueByState(metric);
  const rows = q.data?.data;

  const fmt = (v: number) =>
    metric === "freight_pct" ? fmtPct(v) : metric === "orders" ? fmtInt(v) : fmtBRLCompact(v);

  // Sort client-side by the active metric so the bar order follows the toggle.
  const sorted = rows ? [...rows].sort((a, b) => b.value - a.value) : rows;

  return (
    <ChartCard<StateRow>
      title="Revenue by state"
      subtitle={`${UNIT[metric]} — bar (map fallback)`}
      controls={
        <CardControls>
          <Segmented<Metric>
            ariaLabel="metric"
            value={metric}
            onChange={setMetric}
            options={[
              { label: "GMV", value: "gmv" },
              { label: "Orders", value: "orders" },
              { label: "AOV", value: "aov" },
              { label: "Freight%", value: "freight_pct" },
            ]}
          />
        </CardControls>
      }
      query={q}
      rows={sorted}
    >
      {(data) => (
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 8 }}>
            <XAxis dataKey="state" interval={0} tick={{ fontSize: 10 }} />
            <YAxis tickFormatter={fmt} tick={{ fontSize: 11 }} width={56} />
            <Tooltip formatter={(v: number) => [fmt(v), UNIT[metric]]} />
            <Bar dataKey="value" radius={[3, 3, 0, 0]}>
              {data.map((r) => (
                <Cell key={r.state} fill={r.state === "SP" ? SERIES.accent : SERIES.gmv} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </ChartCard>
  );
}
