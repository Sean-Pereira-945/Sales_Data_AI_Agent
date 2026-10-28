import {
  Bar,
  BarChart,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useDelayVsReview } from "../../api/hooks";
import type { DelayReviewRow } from "../../api/types";
import { DELAY_COLORS } from "../../lib/colors";
import { fmtInt, fmtStars } from "../../lib/format";
import { ChartCard } from "../ChartCard";

export function DelayVsReviewChart() {
  const q = useDelayVsReview();
  const rows = q.data?.data;

  return (
    <ChartCard<DelayReviewRow>
      title="★ Delivery delay → review score"
      subtitle="Avg review (★) by delay bucket · delivered orders with a review"
      query={q}
      rows={rows}
      isEmpty={(r) => r.every((x) => x.orders === 0)}
      insightId="delay-vs-review"
    >
      {(data) => (
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={data} margin={{ top: 20, right: 12, bottom: 4, left: 8 }}>
            <XAxis dataKey="delay_bucket" tick={{ fontSize: 11 }} interval={0} />
            <YAxis domain={[0, 5]} tick={{ fontSize: 11 }} width={32} />
            <Tooltip
              formatter={(v: number, n: string) =>
                n === "avg_review" ? [fmtStars(v), "Avg review"] : [fmtInt(v), "Orders"]
              }
            />
            <Bar dataKey="avg_review" radius={[4, 4, 0, 0]}>
              {data.map((r) => (
                <Cell key={r.delay_bucket} fill={DELAY_COLORS[r.delay_bucket] ?? "#94a3b8"} />
              ))}
              <LabelList
                dataKey="orders"
                position="top"
                formatter={(v: number) => `n=${fmtInt(v)}`}
                style={{ fontSize: 10, fill: "var(--muted)" }}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </ChartCard>
  );
}
