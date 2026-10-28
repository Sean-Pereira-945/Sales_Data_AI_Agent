import { useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useSellerConcentration } from "../../api/hooks";
import type { SellerParetoRow } from "../../api/types";
import { SERIES } from "../../lib/colors";
import { ChartCard } from "../ChartCard";
import { CardControls, Segmented } from "../ui";

export function SellerConcentrationChart() {
  const [buckets, setBuckets] = useState(20);
  const q = useSellerConcentration(buckets);
  const rows = q.data?.data;

  // Prepend the origin so the Pareto curve starts at (0,0).
  const data = rows ? [{ seller_pct: 0, cum_gmv_pct: 0, sellers: 0 }, ...rows] : rows;

  return (
    <ChartCard<SellerParetoRow>
      title="Seller concentration (Pareto)"
      subtitle="Cumulative GMV % by seller rank — platform-dependency risk"
      controls={
        <CardControls>
          <Segmented<number>
            ariaLabel="buckets"
            value={buckets}
            onChange={setBuckets}
            options={[
              { label: "10", value: 10 },
              { label: "20", value: 20 },
              { label: "50", value: 50 },
            ]}
          />
        </CardControls>
      }
      query={q}
      rows={data}
    >
      {(d) => (
        <ResponsiveContainer width="100%" height={260}>
          <AreaChart data={d} margin={{ top: 8, right: 16, bottom: 4, left: 8 }}>
            <defs>
              <linearGradient id="pareto" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={SERIES.gmv} stopOpacity={0.35} />
                <stop offset="100%" stopColor={SERIES.gmv} stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" />
            <XAxis
              dataKey="seller_pct"
              type="number"
              domain={[0, 100]}
              tickFormatter={(v) => `${Math.round(v)}%`}
              tick={{ fontSize: 11 }}
            />
            <YAxis domain={[0, 100]} tickFormatter={(v) => `${Math.round(v)}%`} tick={{ fontSize: 11 }} width={40} />
            <ReferenceLine x={20} stroke="var(--muted)" strokeDasharray="4 4" label={{ value: "top 20%", fontSize: 10, fill: "var(--muted)" }} />
            <Tooltip
              formatter={(v: number) => [`${v.toFixed(1)}%`, "Cumulative GMV"]}
              labelFormatter={(l) => `Top ${Number(l).toFixed(0)}% of sellers`}
            />
            <Area type="monotone" dataKey="cum_gmv_pct" stroke={SERIES.gmv} strokeWidth={2} fill="url(#pareto)" />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </ChartCard>
  );
}
