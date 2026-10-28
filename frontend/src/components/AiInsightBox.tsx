import { useState } from "react";
import { useChartInsight } from "../api/hooks";
import type { QueryValue } from "../api/client";

/**
 * Per-card AI insight. Generated on demand (one click) so a dashboard load or a
 * filter change doesn't fire an LLM call for every card; the result is cached
 * server-side by hash(chart_id + params).
 */
export function AiInsightBox({
  chartId,
  params = {},
}: {
  chartId: string;
  params?: Record<string, QueryValue>;
}) {
  const [open, setOpen] = useState(false);
  const q = useChartInsight(chartId, params, open);

  return (
    <div className="ai-insight">
      <span className="ai-badge">AI</span>
      {!open ? (
        <button className="ai-generate" type="button" onClick={() => setOpen(true)}>
          Generate insight
        </button>
      ) : q.isPending ? (
        <span className="ai-text ai-thinking">Analyzing the numbers…</span>
      ) : q.isError ? (
        <span className="ai-text">Couldn’t generate an insight right now.</span>
      ) : (
        <span className="ai-text ai-filled">{q.data?.insight}</span>
      )}
    </div>
  );
}
