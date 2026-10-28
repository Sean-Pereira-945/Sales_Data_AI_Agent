import { useState } from "react";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useTopCategories } from "../../api/hooks";
import type { TopCategoryRow } from "../../api/types";
import { colorAt } from "../../lib/colors";
import { fmtBRLCompact, fmtInt, fmtStars, humanize } from "../../lib/format";
import { ChartCard } from "../ChartCard";
import { CardControls, Segmented } from "../ui";

type Metric = "gmv" | "orders" | "aov" | "avg_review";

const UNIT: Record<Metric, string> = {
  gmv: "GMV (R$)",
  orders: "Orders",
  aov: "AOV (R$)",
  avg_review: "Avg review (★, min 30 orders)",
};

export function TopCategoriesChart() {
  const [topN, setTopN] = useState(10);
  const [metric, setMetric] = useState<Metric>("gmv");
  const q = useTopCategories(topN, metric);
  const rows = q.data?.data;

  const fmt = (v: number) =>
    metric === "avg_review" ? fmtStars(v) : metric === "orders" ? fmtInt(v) : fmtBRLCompact(v);

  return (
    <ChartCard<TopCategoryRow>
      title="Top categories"
      subtitle={`${UNIT[metric]}, top ${topN}`}
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
              { label: "★", value: "avg_review" },
            ]}
          />
          <Segmented<number>
            ariaLabel="top N"
            value={topN}
            onChange={setTopN}
            options={[
              { label: "5", value: 5 },
              { label: "10", value: 10 },
              { label: "20", value: 20 },
            ]}
          />
        </CardControls>
      }
      query={q}
      rows={rows}
      insightId="top-categories"
      insightParams={{ top_n: topN, metric }}
    >
      {(data) => (
        <ResponsiveContainer width="100%" height={Math.max(220, data.length * 26)}>
          <BarChart data={data} layout="vertical" margin={{ top: 4, right: 48, bottom: 4, left: 8 }}>
            <XAxis type="number" tickFormatter={fmt} tick={{ fontSize: 11 }} />
            <YAxis
              type="category"
              dataKey="category"
              width={150}
              tick={{ fontSize: 11 }}
              tickFormatter={humanize}
            />
            <Tooltip
              formatter={(v: number) => [fmt(v), UNIT[metric]]}
              labelFormatter={(l) => humanize(String(l))}
            />
            <Bar dataKey="value" radius={[0, 4, 4, 0]}>
              {data.map((_, i) => (
                <Cell key={i} fill={colorAt(i)} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </ChartCard>
  );
}
