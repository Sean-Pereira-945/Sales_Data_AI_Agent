import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useReviewDistribution } from "../../api/hooks";
import type { ReviewDistRow, ReviewTrendRow } from "../../api/types";
import { REVIEW_COLORS, SERIES } from "../../lib/colors";
import { fmtInt, fmtPeriod, fmtStars } from "../../lib/format";
import { ChartCard } from "../ChartCard";
import { CardControls, Segmented } from "../ui";

type View = "distribution" | "trend";

export function ReviewDistributionChart() {
  const [view, setView] = useState<View>("distribution");
  const q = useReviewDistribution(view);
  const rows = q.data?.data;

  return (
    <ChartCard
      title="Review score distribution"
      subtitle={view === "trend" ? "Avg review (★) & 1★ share, monthly" : "Count of reviews by score (1–5★)"}
      controls={
        <CardControls>
          <Segmented<View>
            ariaLabel="view"
            value={view}
            onChange={setView}
            options={[
              { label: "Distribution", value: "distribution" },
              { label: "Trend", value: "trend" },
            ]}
          />
        </CardControls>
      }
      query={q}
      rows={rows}
      insightId="review-distribution"
      insightParams={{ view }}
    >
      {() =>
        view === "distribution" ? (
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={rows as ReviewDistRow[]} margin={{ top: 8, right: 12, bottom: 4, left: 8 }}>
              <XAxis dataKey="score" tickFormatter={(v) => `${v}★`} tick={{ fontSize: 11 }} />
              <YAxis tickFormatter={fmtInt} tick={{ fontSize: 11 }} width={48} />
              <Tooltip formatter={(v: number) => [fmtInt(v), "Reviews"]} labelFormatter={(l) => `${l}★`} />
              <Bar dataKey="reviews" radius={[4, 4, 0, 0]}>
                {(rows as ReviewDistRow[]).map((r) => (
                  <Cell key={r.score} fill={REVIEW_COLORS[r.score] ?? "#94a3b8"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <ResponsiveContainer width="100%" height={260}>
            <ComposedChart data={rows as ReviewTrendRow[]} margin={{ top: 8, right: 12, bottom: 4, left: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" />
              <XAxis dataKey="period" tickFormatter={fmtPeriod} minTickGap={20} tick={{ fontSize: 11 }} />
              <YAxis yAxisId="l" domain={[0, 5]} tick={{ fontSize: 11 }} width={32} />
              <YAxis yAxisId="r" orientation="right" tickFormatter={(v) => `${Math.round(v)}%`} tick={{ fontSize: 11 }} width={40} />
              <Tooltip
                labelFormatter={(l) => fmtPeriod(String(l))}
                formatter={(v: number, n: string) =>
                  n === "avg_review" ? [fmtStars(v), "Avg review"] : [`${v.toFixed(1)}%`, "1★ share"]
                }
              />
              <Line yAxisId="l" type="monotone" dataKey="avg_review" name="avg_review" stroke={SERIES.aov} dot={false} strokeWidth={2} />
              <Line yAxisId="r" type="monotone" dataKey="one_star_pct" name="one_star_pct" stroke={SERIES.warn} dot={false} strokeWidth={2} />
            </ComposedChart>
          </ResponsiveContainer>
        )
      }
    </ChartCard>
  );
}
