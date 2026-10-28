import { isPartialPeriod, useFilters } from "../state/filters";

export function PartialPeriodWarning() {
  const { filters } = useFilters();
  if (!isPartialPeriod(filters)) return null;
  return (
    <div className="warn-banner" role="status">
      ⚠️ Partial period: your date range reaches outside 2017-01-01 – 2018-08-31, where the
      data is sparse (pre-2017) or truncated (after Aug 2018). Totals and comparisons for those
      edges are not reliable.
    </div>
  );
}
