import { useEffect, useRef, useState, type ReactNode } from "react";
import { humanize } from "../lib/format";

/** A small segmented control for local chart toggles. */
export function Segmented<T extends string | number>({
  value,
  options,
  onChange,
  ariaLabel,
}: {
  value: T;
  options: { label: string; value: T }[];
  onChange: (v: T) => void;
  ariaLabel?: string;
}) {
  return (
    <div className="segmented" role="group" aria-label={ariaLabel}>
      {options.map((o) => (
        <button
          key={String(o.value)}
          className={o.value === value ? "seg active" : "seg"}
          aria-pressed={o.value === value}
          onClick={() => onChange(o.value)}
          type="button"
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Skeleton({ height = 240 }: { height?: number }) {
  return <div className="skeleton" style={{ height }} aria-hidden="true" />;
}

export function EmptyState({ message = "No orders match these filters" }: { message?: string }) {
  return <div className="empty">{message}</div>;
}

export function ErrorState({ error }: { error: unknown }) {
  const msg = error instanceof Error ? error.message : String(error);
  return (
    <div className="error-box" role="alert">
      <strong>Couldn’t load this chart.</strong>
      <pre>{msg}</pre>
    </div>
  );
}

/** Checkbox dropdown for multi-select filters (states, categories, statuses). */
export function MultiSelect({
  label,
  options,
  selected,
  onChange,
  humanizeLabels = false,
  width = 200,
}: {
  label: string;
  options: string[];
  selected: string[];
  onChange: (next: string[]) => void;
  humanizeLabels?: boolean;
  width?: number;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const toggle = (opt: string) =>
    onChange(selected.includes(opt) ? selected.filter((s) => s !== opt) : [...selected, opt]);

  const summary =
    selected.length === 0 ? "All" : selected.length <= 2 ? selected.join(", ") : `${selected.length} selected`;

  return (
    <div className="multiselect" ref={ref} style={{ width }}>
      <label className="field-label">{label}</label>
      <button className="ms-trigger" onClick={() => setOpen((o) => !o)} type="button" aria-expanded={open}>
        <span className="ms-summary">{summary}</span>
        <span className="ms-caret">▾</span>
      </button>
      {open && (
        <div className="ms-menu" role="listbox">
          {selected.length > 0 && (
            <button className="ms-clear" type="button" onClick={() => onChange([])}>
              Clear
            </button>
          )}
          {options.map((opt) => (
            <label key={opt} className="ms-option">
              <input type="checkbox" checked={selected.includes(opt)} onChange={() => toggle(opt)} />
              <span>{humanizeLabels ? humanize(opt) : opt}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

export function CardControls({ children }: { children: ReactNode }) {
  return <div className="card-controls">{children}</div>;
}
