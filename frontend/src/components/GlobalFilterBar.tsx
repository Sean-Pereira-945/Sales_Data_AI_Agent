import { useFiltersMeta } from "../api/hooks";
import { useFilters } from "../state/filters";
import { MultiSelect } from "./ui";

export function GlobalFilterBar() {
  const { filters, setFilters, reset } = useFilters();
  const meta = useFiltersMeta();

  const states = meta.data?.states ?? [];
  const categories = meta.data?.categories ?? [];
  const statuses = meta.data?.statuses ?? [];
  const dateMin = meta.data?.date_min;
  const dateMax = meta.data?.date_max;

  return (
    <div className="filterbar">
      <div className="field">
        <label className="field-label">From</label>
        <input
          type="date"
          value={filters.dateFrom}
          min={dateMin}
          max={dateMax}
          onChange={(e) => setFilters({ dateFrom: e.target.value })}
        />
      </div>
      <div className="field">
        <label className="field-label">To</label>
        <input
          type="date"
          value={filters.dateTo}
          min={dateMin}
          max={dateMax}
          onChange={(e) => setFilters({ dateTo: e.target.value })}
        />
      </div>

      <MultiSelect
        label="State"
        options={states}
        selected={filters.states}
        onChange={(states) => setFilters({ states })}
        width={160}
      />
      <MultiSelect
        label="Category"
        options={categories}
        selected={filters.categories}
        onChange={(categories) => setFilters({ categories })}
        humanizeLabels
        width={200}
      />
      <MultiSelect
        label="Status"
        options={statuses}
        selected={filters.statuses}
        onChange={(statuses) => setFilters({ statuses })}
        width={180}
      />

      <button className="btn-ghost reset" type="button" onClick={reset}>
        Reset
      </button>
    </div>
  );
}
