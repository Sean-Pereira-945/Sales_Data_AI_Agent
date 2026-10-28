// Response shapes from the Phase 1 dashboard API (see docs/API.md).

export interface FiltersMeta {
  states: string[];
  categories: string[];
  statuses: string[];
  date_min: string;
  date_max: string;
  default_date_from: string;
  default_date_to: string;
  default_statuses: string[];
  currency: string;
}

export interface KpiCard {
  key: string;
  label: string;
  unit: string | null;
  value: number | null;
  prev_value: number | null;
  delta_pct: number | null;
}

export interface KpiResponse {
  cards: KpiCard[];
  comparison_label: string | null;
  partial_period: boolean;
  currency: string;
}

export interface ChartResponse<Row> {
  data: Row[];
  meta: Record<string, unknown>;
}

export interface TrendRow {
  period: string;
  gmv: number;
  orders: number;
  aov: number;
}

export interface TopCategoryRow {
  category: string;
  value: number;
  orders: number;
  gmv?: number;
}

export interface StateRow {
  state: string;
  value: number;
  gmv: number;
  orders: number;
  aov: number;
  freight_pct: number;
}

export interface PaymentShareRow {
  period: string;
  payment_type: string;
  orders: number;
  gmv: number;
}

export interface InstallmentRow {
  installments: number;
  orders: number;
  avg_order_value: number;
}

export interface DelayReviewRow {
  delay_bucket: string;
  avg_review: number | null;
  orders: number;
}

export interface LateStateRow {
  state: string;
  late_pct: number;
  avg_delivery_days: number | null;
  orders: number;
}

export interface ReviewDistRow {
  score: number;
  reviews: number;
}

export interface ReviewTrendRow {
  period: string;
  avg_review: number | null;
  one_star_pct: number;
  reviews: number;
}

export interface SellerParetoRow {
  seller_pct: number;
  cum_gmv_pct: number | null;
  sellers: number;
}

export interface InsightResponse {
  chart_id: string;
  insight: string;
  model: string;
  facts: string[];
}

export interface SummaryResponse {
  summary: string;
  model: string;
}

export interface ChartSpec {
  type: "line" | "bar" | "area" | "pie";
  x: string;
  y: string;
  series: string | null;
}

// A streamed chat turn assembled on the client from SSE events.
export interface ChatFinal {
  type: "final";
  thread_id: string;
  intent: string | null;
  sql: string | null;
  insight: string;
  chart_spec: ChartSpec | null;
  row_count: number;
  data: Record<string, unknown>[];
  report_id: string | null;
}

export interface ReportResponse {
  id: string;
  title: string;
  topic: string;
  created_at: string;
  sections: string[];
  markdown: string;
  pdf_url: string;
  markdown_url: string;
}
