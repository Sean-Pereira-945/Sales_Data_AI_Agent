import { buildQuery, type QueryValue } from "./client";
import type { ReportResponse } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

/** Generate a report for a topic under the current global filters. */
export async function generateReport(
  topic: string,
  filterParams: Record<string, QueryValue>,
): Promise<ReportResponse> {
  const res = await fetch(`${API_BASE}/api/reports${buildQuery(filterParams)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic }),
  });
  if (!res.ok) throw new Error(`Report generation failed (HTTP ${res.status})`);
  return res.json() as Promise<ReportResponse>;
}

/** Absolute (proxy-relative) URL for a report download. */
export function reportDownloadUrl(path: string): string {
  return `${API_BASE}${path}`;
}
