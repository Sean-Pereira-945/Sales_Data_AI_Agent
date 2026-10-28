import { useState } from "react";
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useTrend } from "../../api/hooks";
import type { TrendRow } from "../../api/types";
import { SERIES } from "../../lib/colors";
import { fmtBRL, fmtBRLCompact, fmtInt, fmtPeriod } from "../../lib/format";
import { ChartCard } from "../ChartCard";
import { CardControls, Segmented } from "../ui";

type Gran = "day" | "week" | "month";
type Metric = "gmv" | "orders" | "aov";

export function TrendChart() {
  const [granularity, setGranularity] = useState<Gran>("month");
  const [metric, setMetric] = useState<Metric>("gmv");
  const q = useTrend(granularity);
  const rows = q.data?.data;

  return (
    <ChartCard<TrendRow>
      title="GMV & Orders trend"
      subtitle={`${metric === "aov" ? "AOV (R$)" : metric === "orders" ? "Orders" : "GMV (R$)"}, ${granularity}`}
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
            ]}
          />
          <Segmented<Gran>
            ariaLabel="granularity"
            value={granularity}
            onChange={setGranularity}
            options={[
              { label: "D", value: "day" },
              { label: "W", value: "week" },
              { label: "M", value: "month" },
            ]}
          />
        </CardControls>
      }
      query={q}
      rows={rows}
    >
      {(data) => (
        <ResponsiveContainer width="100%" height={260}>
          <ComposedChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" />
            <XAxis
              dataKey="period"
              tickFormatter={granularity === "month" ? fmtPeriod : undefined}
              minTickGap={24}
              tick={{ fontSize: 11 }}
            />
            {metric === "gmv" && (
              <>
                <YAxis yAxisId="l" tickFormatter={fmtBRLCompact} tick={{ fontSize: 11 }} width={56} />
                <YAxis
                  yAxisId="r"
                  orientation="right"
                  tickFormatter={(v) => fmtInt(v)}
                  tick={{ fontSize: 11 }}
                  width={48}
                />
                <Line yAxisId="l" type="monotone" dataKey="gmv" name="GMV (R$)" stroke={SERIES.gmv} dot={false} strokeWidth={2} />
                <Line yAxisId="r" type="monotone" dataKey="orders" name="Orders" stroke={SERIES.orders} dot={false} strokeWidth={2} />
              </>
            )}
            {metric === "orders" && (
              <>
                <YAxis tickFormatter={(v) => fmtInt(v)} tick={{ fontSize: 11 }} width={48} />
                <Line type="monotone" dataKey="orders" name="Orders" stroke={SERIES.orders} dot={false} strokeWidth={2} />
              </>
            )}
            {metric === "aov" && (
              <>
                <YAxis tickFormatter={fmtBRLCompact} tick={{ fontSize: 11 }} width={56} />
                <Line type="monotone" dataKey="aov" name="AOV (R$)" stroke={SERIES.aov} dot={false} strokeWidth={2} />
              </>
            )}
            <Tooltip
              labelFormatter={(l) => (granularity === "month" ? fmtPeriod(String(l)) : String(l))}
              formatter={(value: number, name: string) =>
                name === "Orders" ? [fmtInt(value), name] : [fmtBRL(value, true), name]
              }
            />
          </ComposedChart>
        </ResponsiveContainer>
      )}
    </ChartCard>
  );
}
