import type { ReactNode } from "react";
import type { QueryValue } from "../api/client";
import { AiInsightBox } from "./AiInsightBox";
import { EmptyState, ErrorState, Skeleton } from "./ui";

/**
 * Generic chart card: title (with its unit), optional local controls, a body
 * that handles loading / error / empty, and a per-chart AI-insight placeholder
 * (wired to real insights in Phase 4).
 */
export function ChartCard<Row>({
  title,
  subtitle,
  controls,
  query,
  rows,
  isEmpty,
  children,
  height = 260,
  insightId,
  insightParams,
}: {
  title: string;
  subtitle?: string;
  controls?: ReactNode;
  query: { isPending: boolean; isError: boolean; error: unknown; isFetching: boolean; data: unknown };
  rows: Row[] | undefined;
  isEmpty?: (rows: Row[]) => boolean;
  children: (rows: Row[]) => ReactNode;
  height?: number;
  insightId?: string;
  insightParams?: Record<string, QueryValue>;
}) {
  const empty = rows && (isEmpty ? isEmpty(rows) : rows.length === 0);

  return (
    <section className="card">
      <header className="card-head">
        <div className="card-titles">
          <h3>{title}</h3>
          {subtitle && <p className="card-sub">{subtitle}</p>}
        </div>
        <div className="card-head-right">
          {query.isFetching && !query.isPending && <span className="refetch-dot" title="Refreshing…" />}
          {controls}
        </div>
      </header>

      <div className="card-body" style={{ minHeight: height }}>
        {query.isPending ? (
          <Skeleton height={height} />
        ) : query.isError ? (
          <ErrorState error={query.error} />
        ) : empty || !rows ? (
          <EmptyState />
        ) : (
          children(rows)
        )}
      </div>

      {insightId && <AiInsightBox chartId={insightId} params={insightParams} />}
    </section>
  );
}
