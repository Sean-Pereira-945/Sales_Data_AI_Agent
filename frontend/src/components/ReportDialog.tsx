import { useState } from "react";
import { generateReport, reportDownloadUrl } from "../api/reports";
import type { ReportResponse } from "../api/types";
import { filtersToParams, useFilters } from "../state/filters";

const SUGGESTIONS = [
  "Q3 regional performance",
  "Delivery & logistics review",
  "Product category deep dive",
  "Customer experience & reviews",
];

export function ReportDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { filters } = useFilters();
  const [topic, setTopic] = useState("Sales overview");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<ReportResponse | null>(null);

  if (!open) return null;

  const run = async () => {
    setBusy(true);
    setError(null);
    setReport(null);
    try {
      setReport(await generateReport(topic.trim() || "Sales overview", filtersToParams(filters)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "error");
    }
    setBusy(false);
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Generate report">
        <header className="modal-head">
          <h3>Generate report</h3>
          <button className="btn-ghost chat-x" onClick={onClose} aria-label="Close">✕</button>
        </header>

        <div className="modal-body">
          <label className="field-label">Topic</label>
          <input
            className="report-topic"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="e.g. Q3 regional performance"
            disabled={busy}
          />
          <div className="report-suggestions">
            {SUGGESTIONS.map((s) => (
              <button key={s} className="chip" type="button" onClick={() => setTopic(s)} disabled={busy}>
                {s}
              </button>
            ))}
          </div>
          <p className="report-note">
            Uses the current global filters. The agent plans sections, runs the queries,
            renders charts, and writes the narrative.
          </p>

          {error && <div className="error-box">{error}</div>}

          {report && (
            <div className="report-result">
              <div className="report-title">{report.title}</div>
              <ul className="report-sections">
                {report.sections.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
              <div className="report-downloads">
                <a className="btn" href={reportDownloadUrl(report.pdf_url)} target="_blank" rel="noreferrer">
                  Download PDF
                </a>
                <a className="btn-ghost" href={reportDownloadUrl(report.markdown_url)} target="_blank" rel="noreferrer">
                  Download Markdown
                </a>
              </div>
            </div>
          )}
        </div>

        <footer className="modal-foot">
          <button className="btn" type="button" onClick={run} disabled={busy}>
            {busy ? "Generating…" : report ? "Regenerate" : "Generate"}
          </button>
          <button className="btn-ghost" type="button" onClick={onClose} disabled={busy}>
            Close
          </button>
        </footer>
      </div>
    </div>
  );
}
