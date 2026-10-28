import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { getJson, type QueryValue } from "./client";
import { filtersToParams, useFilters, type Filters } from "../state/filters";
import type {
  ChartResponse,
  DelayReviewRow,
  FiltersMeta,
  InsightResponse,
  InstallmentRow,
  KpiResponse,
  LateStateRow,
  PaymentShareRow,
  ReviewDistRow,
  ReviewTrendRow,
  SellerParetoRow,
  StateRow,
  TopCategoryRow,
  TrendRow,
} from "./types";

type Local = Record<string, QueryValue>;

// A shared query config: keep the previous data visible while refetching so a
// filter change doesn't blank the charts (DASHBOARD_SPEC.md §10).
const common = {
  placeholderData: keepPreviousData,
  staleTime: 60_000,
  retry: 1,
} as const;

function useChart<T>(id: string, path: string, local: Local = {}) {
  const { filters } = useFilters();
  const params = { ...filtersToParams(filters), ...local };
  return useQuery({
    queryKey: ["chart", id, filterKey(filters), local],
    queryFn: () => getJson<T>(path, params),
    ...common,
  });
}

function filterKey(f: Filters) {
  return [f.dateFrom, f.dateTo, f.states.join(","), f.categories.join(","), f.statuses.join(",")];
}

export function useFiltersMeta() {
  return useQuery({
    queryKey: ["filters-meta"],
    queryFn: () => getJson<FiltersMeta>("/api/filters/meta"),
    staleTime: Infinity,
  });
}

export function useKpis() {
  const { filters } = useFilters();
  return useQuery({
    queryKey: ["kpis", filterKey(filters)],
    queryFn: () => getJson<KpiResponse>("/api/kpis", filtersToParams(filters)),
    ...common,
  });
}

export const useTrend = (granularity: string) =>
  useChart<ChartResponse<TrendRow>>("trend", "/api/charts/trend", { granularity });

export const useTopCategories = (top_n: number, metric: string) =>
  useChart<ChartResponse<TopCategoryRow>>("top-categories", "/api/charts/top-categories", {
    top_n,
    metric,
  });

export const useRevenueByState = (metric: string) =>
  useChart<ChartResponse<StateRow>>("revenue-by-state", "/api/charts/revenue-by-state", { metric });

export const usePaymentMix = (view: string) =>
  useChart<ChartResponse<PaymentShareRow | InstallmentRow>>(
    "payment-mix",
    "/api/charts/payment-mix",
    { view },
  );

export const useDelayVsReview = () =>
  useChart<ChartResponse<DelayReviewRow>>("delay-vs-review", "/api/charts/delay-vs-review");

export const useLateByState = (min_orders: number, sort: string) =>
  useChart<ChartResponse<LateStateRow>>("late-by-state", "/api/charts/late-by-state", {
    min_orders,
    sort,
  });

export const useReviewDistribution = (view: string) =>
  useChart<ChartResponse<ReviewDistRow | ReviewTrendRow>>(
    "review-distribution",
    "/api/charts/review-distribution",
    { view },
  );

export const useSellerConcentration = (buckets: number) =>
  useChart<ChartResponse<SellerParetoRow>>(
    "seller-concentration",
    "/api/charts/seller-concentration",
    { buckets },
  );

// ---- AI insights (Phase 4) ----
const insightCommon = { staleTime: 5 * 60_000, retry: 0 } as const;

/** Per-chart AI insight, computed from the same aggregated data the chart shows. */
export function useChartInsight(chartId: string, local: Local = {}, enabled = true) {
  const { filters } = useFilters();
  const params = { ...filtersToParams(filters), ...local };
  return useQuery({
    queryKey: ["insight", chartId, filterKey(filters), local],
    queryFn: () => getJson<InsightResponse>(`/api/insights/${chartId}`, params),
    enabled,
    ...insightCommon,
  });
}

export function useKpiInsight(enabled = true) {
  const { filters } = useFilters();
  return useQuery({
    queryKey: ["insight", "kpis", filterKey(filters)],
    queryFn: () => getJson<InsightResponse>("/api/insights/kpis", filtersToParams(filters)),
    enabled,
    ...insightCommon,
  });
}
