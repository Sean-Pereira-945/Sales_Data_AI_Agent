import { useState } from "react";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useLateByState } from "../../api/hooks";
import type { LateStateRow } from "../../api/types";
import { SERIES } from "../../lib/colors";
import { fmtPct } from "../../lib/format";
import { ChartCard } from "../ChartCard";
import { CardControls, Segmented } from "../ui";

type Sort = "late_pct" | "delivery_days" | "orders";

export function LateByStateChart() {
  const [minOrders, setMinOrders] = useState(30);
  const [sort, setSort] = useState<Sort>("late_pct");
  const q = useLateByState(minOrders, sort);
  const rows = q.data?.data;

  return (
    <ChartCard<LateStateRow>
      title="Late % by state"
      subtitle="Late delivery % (bars) · avg delivery days (line)"
      controls={
        <CardControls>
          <Segmented<Sort>
            ariaLabel="sort"
            value={sort}
            onChange={setSort}
            options={[
              { label: "Late%", value: "late_pct" },
              { label: "Days", value: "delivery_days" },
              { label: "Orders", value: "orders" },
            ]}
          />
          <Segmented<number>
            ariaLabel="min orders"
            value={minOrders}
            onChange={setMinOrders}
            options={[
              { label: "≥0", value: 0 },
              { label: "≥30", value: 30 },
              { label: "≥100", value: 100 },
            ]}
          />
        </CardControls>
      }
      query={q}
      rows={rows}
    >
      {(data) => (
        <ResponsiveContainer width="100%" height={260}>
          <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" />
            <XAxis dataKey="state" interval={0} tick={{ fontSize: 10 }} />
            <YAxis yAxisId="l" tickFormatter={(v) => `${Math.round(v)}%`} tick={{ fontSize: 11 }} width={40} />
            <YAxis yAxisId="r" orientation="right" tick={{ fontSize: 11 }} width={32} />
            <Tooltip
              formatter={(v: number, n: string) =>
                n === "late_pct" ? [fmtPct(v), "Late %"] : [`${v.toFixed(1)} d`, "Avg delivery days"]
              }
            />
            <Bar yAxisId="l" dataKey="late_pct" name="late_pct" fill={SERIES.warn} radius={[3, 3, 0, 0]} />
            <Line
              yAxisId="r"
              type="monotone"
              dataKey="avg_delivery_days"
              name="avg_delivery_days"
              stroke={SERIES.accent}
              dot={false}
              strokeWidth={2}
            />
          </ComposedChart>
        </ResponsiveContainer>
      )}
    </ChartCard>
  );
}
