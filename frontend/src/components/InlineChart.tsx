import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ChartSpec } from "../api/types";
import { SERIES } from "../lib/colors";
import { fmtBRLCompact, fmtPeriod } from "../lib/format";

/** Small chart rendered inline in a chat answer from the agent's chart_spec. */
export function InlineChart({
  spec,
  data,
}: {
  spec: ChartSpec;
  data: Record<string, unknown>[];
}) {
  if (!data?.length || !(spec.x in data[0]) || !(spec.y in data[0])) return null;

  const rows = data.map((r) => ({ ...r, [spec.y]: Number(r[spec.y]) }));
  const temporal = /month|period|date|day|week/i.test(spec.x);
  const tickFmt = temporal ? (v: string) => fmtPeriod(String(v)) : undefined;

  return (
    <div className="inline-chart">
      <ResponsiveContainer width="100%" height={180}>
        {spec.type === "line" || spec.type === "area" ? (
          <LineChart data={rows} margin={{ top: 8, right: 10, bottom: 2, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" />
            <XAxis dataKey={spec.x} tickFormatter={tickFmt} tick={{ fontSize: 10 }} minTickGap={20} />
            <YAxis tickFormatter={(v) => fmtBRLCompact(Number(v))} tick={{ fontSize: 10 }} width={48} />
            <Tooltip labelFormatter={(l) => (temporal ? fmtPeriod(String(l)) : String(l))} />
            <Line type="monotone" dataKey={spec.y} stroke={SERIES.gmv} dot={false} strokeWidth={2} />
          </LineChart>
        ) : (
          <BarChart data={rows} margin={{ top: 8, right: 10, bottom: 2, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" />
            <XAxis dataKey={spec.x} tickFormatter={tickFmt} tick={{ fontSize: 10 }} interval={0} />
            <YAxis tick={{ fontSize: 10 }} width={40} />
            <Tooltip />
            <Bar dataKey={spec.y} fill={SERIES.gmv} radius={[3, 3, 0, 0]} />
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}
