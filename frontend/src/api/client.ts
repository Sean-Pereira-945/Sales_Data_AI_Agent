// Minimal fetch wrapper. Requests are same-origin in dev (Vite proxies /api to
// the backend) and can target VITE_API_BASE in other environments.

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

export type QueryValue = string | number | boolean | undefined | null;

export function buildQuery(params: Record<string, QueryValue>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

export async function getJson<T>(path: string, params: Record<string, QueryValue> = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}${buildQuery(params)}`);
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText} — ${path}\n${body.slice(0, 300)}`);
  }
  return res.json() as Promise<T>;
}
