// A single categorical palette, plus fixed mappings so a given payment type /
// delay bucket / review score keeps the same colour across every chart
// (DASHBOARD_SPEC.md §10).

export const SERIES = {
  gmv: "#2563eb", // blue
  orders: "#f59e0b", // amber
  aov: "#10b981", // emerald
  accent: "#7c3aed", // violet
  warn: "#ef4444", // red
};

// Brand-neutral categorical palette for arbitrary dimensions (states, sellers).
export const PALETTE = [
  "#2563eb", "#10b981", "#f59e0b", "#7c3aed", "#ef4444",
  "#0ea5e9", "#84cc16", "#ec4899", "#14b8a6", "#f97316",
];

export function colorAt(i: number): string {
  return PALETTE[i % PALETTE.length];
}

export const PAYMENT_COLORS: Record<string, string> = {
  credit_card: "#2563eb",
  boleto: "#10b981",
  voucher: "#f59e0b",
  debit_card: "#7c3aed",
  not_defined: "#94a3b8",
  unknown: "#94a3b8",
};

// Sequential red->green: worse delay is redder.
export const DELAY_COLORS: Record<string, string> = {
  early: "#16a34a",
  "on time": "#65a30d",
  "1-3 days late": "#f59e0b",
  "4-7 days late": "#f97316",
  "8+ days late": "#dc2626",
};

export const REVIEW_COLORS: Record<number, string> = {
  1: "#dc2626",
  2: "#f97316",
  3: "#f59e0b",
  4: "#84cc16",
  5: "#16a34a",
};
