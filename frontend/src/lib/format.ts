// Formatting helpers. Currency is BRL (R$) throughout (DASHBOARD_SPEC.md).

const brl = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  maximumFractionDigits: 0,
});
const brl2 = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  maximumFractionDigits: 2,
});
const int = new Intl.NumberFormat("en-US");

export function fmtBRL(v: number | null | undefined, cents = false): string {
  if (v === null || v === undefined) return "—";
  return (cents ? brl2 : brl).format(v);
}

export function fmtInt(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return int.format(Math.round(v));
}

/** Compact currency for axis ticks: R$1.2M, R$340k. */
export function fmtBRLCompact(v: number): string {
  const abs = Math.abs(v);
  if (abs >= 1_000_000) return `R$${(v / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `R$${Math.round(v / 1_000)}k`;
  return `R$${Math.round(v)}`;
}

export function fmtPct(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined) return "—";
  return `${v.toFixed(digits)}%`;
}

export function fmtStars(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `${v.toFixed(2)}★`;
}

export function fmtDelta(v: number | null | undefined): string {
  if (v === null || v === undefined) return "";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(1)}%`;
}

/** Humanize a category slug: bed_bath_table -> Bed Bath Table. */
export function humanize(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Month bucket "2017-03-01" -> "Mar 2017"; pass through other granularities. */
export function fmtPeriod(p: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(p);
  if (!m) return p;
  const d = new Date(`${p}T00:00:00`);
  return d.toLocaleDateString("en-US", { month: "short", year: "numeric" });
}
