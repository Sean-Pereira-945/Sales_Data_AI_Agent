import { createContext, useContext, useMemo, useReducer, type ReactNode } from "react";
import type { QueryValue } from "../api/client";

// Spec defaults (DASHBOARD_SPEC.md §4). Empty statuses => backend applies the
// revenue-eligible default.
export const DEFAULT_DATE_FROM = "2017-01-01";
export const DEFAULT_DATE_TO = "2018-08-31";

export interface Filters {
  dateFrom: string;
  dateTo: string;
  states: string[];
  categories: string[];
  statuses: string[];
}

const initialFilters: Filters = {
  dateFrom: DEFAULT_DATE_FROM,
  dateTo: DEFAULT_DATE_TO,
  states: [],
  categories: [],
  statuses: [],
};

type Action =
  | { type: "set"; patch: Partial<Filters> }
  | { type: "reset" };

function reducer(state: Filters, action: Action): Filters {
  switch (action.type) {
    case "set":
      return { ...state, ...action.patch };
    case "reset":
      return initialFilters;
  }
}

interface Ctx {
  filters: Filters;
  setFilters: (patch: Partial<Filters>) => void;
  reset: () => void;
}

const FilterContext = createContext<Ctx | null>(null);

export function FilterProvider({ children }: { children: ReactNode }) {
  const [filters, dispatch] = useReducer(reducer, initialFilters);
  const value = useMemo<Ctx>(
    () => ({
      filters,
      setFilters: (patch) => dispatch({ type: "set", patch }),
      reset: () => dispatch({ type: "reset" }),
    }),
    [filters],
  );
  return <FilterContext.Provider value={value}>{children}</FilterContext.Provider>;
}

export function useFilters(): Ctx {
  const ctx = useContext(FilterContext);
  if (!ctx) throw new Error("useFilters must be used within FilterProvider");
  return ctx;
}

/** Serialize filters to the backend's query params (CSV lists; omit when empty). */
export function filtersToParams(f: Filters): Record<string, QueryValue> {
  return {
    date_from: f.dateFrom,
    date_to: f.dateTo,
    states: f.states.length ? f.states.join(",") : undefined,
    categories: f.categories.length ? f.categories.join(",") : undefined,
    statuses: f.statuses.length ? f.statuses.join(",") : undefined,
  };
}

/** True when the range reaches outside the known-good window (partial period). */
export function isPartialPeriod(f: Filters): boolean {
  return f.dateFrom < DEFAULT_DATE_FROM || f.dateTo > DEFAULT_DATE_TO;
}
