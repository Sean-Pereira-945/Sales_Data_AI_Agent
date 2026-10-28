import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { usePaymentMix } from "../../api/hooks";
import type { InstallmentRow, PaymentShareRow } from "../../api/types";
import { PAYMENT_COLORS, SERIES } from "../../lib/colors";
import { fmtBRLCompact, fmtInt, fmtPeriod } from "../../lib/format";
import { ChartCard } from "../ChartCard";
import { CardControls, Segmented } from "../ui";

type View = "share" | "absolute" | "installments";

interface PivotRow {
  period: string;
  [paymentType: string]: number | string;
}

function pivot(rows: PaymentShareRow[], share: boolean): { data: PivotRow[]; types: string[] } {
  const typeSet = new Set<string>();
  const byPeriod = new Map<string, PivotRow>();
  for (const r of rows) {
    typeSet.add(r.payment_type);
    const row = byPeriod.get(r.period) ?? { period: r.period };
    row[r.payment_type] = (Number(row[r.payment_type]) || 0) + r.orders;
    byPeriod.set(r.period, row);
  }
  const data = [...byPeriod.values()].sort((a, b) => String(a.period).localeCompare(String(b.period)));
  const types = [...typeSet];
  if (share) {
    for (const row of data) {
      const total = types.reduce((s, t) => s + (Number(row[t]) || 0), 0) || 1;
      for (const t of types) row[t] = ((Number(row[t]) || 0) / total) * 100;
    }
  }
  return { data, types };
}

export function PaymentMixChart() {
  const [view, setView] = useState<View>("share");
  const q = usePaymentMix(view);
  const rows = q.data?.data;

  const pivoted = useMemo(
    () => (view !== "installments" && rows ? pivot(rows as PaymentShareRow[], view === "share") : null),
    [rows, view],
  );

  return (
    <ChartCard
      title="Payment mix over time"
      subtitle={
        view === "installments" ? "Orders by installments" : view === "share" ? "% of orders, monthly" : "Orders, monthly"
      }
      controls={
        <CardControls>
          <Segmented<View>
            ariaLabel="view"
            value={view}
            onChange={setView}
            options={[
              { label: "Share", value: "share" },
              { label: "Absolute", value: "absolute" },
              { label: "Installments", value: "installments" },
            ]}
          />
        </CardControls>
      }
      query={q}
      rows={rows}
      insightId="payment-mix"
      insightParams={{ view }}
    >
      {() =>
        view === "installments" ? (
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={rows as InstallmentRow[]} margin={{ top: 8, right: 12, bottom: 4, left: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" />
              <XAxis dataKey="installments" tick={{ fontSize: 11 }} />
              <YAxis tickFormatter={fmtInt} tick={{ fontSize: 11 }} width={48} />
              <Tooltip
                formatter={(v: number, n: string) =>
                  n === "avg_order_value" ? [fmtBRLCompact(v), "Avg order value"] : [fmtInt(v), "Orders"]
                }
                labelFormatter={(l) => `${l} installment(s)`}
              />
              <Bar dataKey="orders" name="Orders" fill={SERIES.gmv} radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={pivoted!.data} margin={{ top: 8, right: 12, bottom: 4, left: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" />
              <XAxis dataKey="period" tickFormatter={fmtPeriod} minTickGap={20} tick={{ fontSize: 11 }} />
              <YAxis
                tickFormatter={(v) => (view === "share" ? `${Math.round(v)}%` : fmtInt(v))}
                tick={{ fontSize: 11 }}
                width={48}
              />
              <Tooltip
                labelFormatter={(l) => fmtPeriod(String(l))}
                formatter={(v: number, n: string) => [view === "share" ? `${v.toFixed(1)}%` : fmtInt(v), n]}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              {pivoted!.types.map((t) => (
                <Bar
                  key={t}
                  dataKey={t}
                  stackId="pay"
                  name={t}
                  fill={PAYMENT_COLORS[t] ?? "#94a3b8"}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        )
      }
    </ChartCard>
  );
}
