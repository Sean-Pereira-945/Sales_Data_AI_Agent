import { useEffect, useRef, useState } from "react";
import { reportDownloadUrl } from "../api/reports";
import type { ChatMessage } from "../hooks/useChat";
import { InlineChart } from "./InlineChart";

/** Side chat panel backed by the LangGraph agent (streaming + thread memory). */
export function ChatPanel({
  open,
  onClose,
  messages,
  busy,
  onSend,
}: {
  open: boolean;
  onClose: () => void;
  messages: ChatMessage[];
  busy: boolean;
  onSend: (text: string) => void;
}) {
  const [draft, setDraft] = useState("");
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const t = draft.trim();
    if (!t || busy) return;
    onSend(t);
    setDraft("");
  };

  return (
    <aside className={open ? "chat open" : "chat"} aria-label="AI chat panel">
      <header className="chat-head">
        <span>Ask the data</span>
        <button className="btn-ghost chat-x" onClick={onClose} aria-label="Close chat">
          ✕
        </button>
      </header>

      <div className="chat-body" ref={bodyRef}>
        {messages.length === 0 && (
          <div className="chat-msg assistant">
            Ask about the sales data — e.g. <em>“monthly GMV trend”</em>,
            <em> “top categories by revenue”</em>, or
            <em> “how does delivery delay affect reviews?”</em>. Answers are grounded only in
            aggregated query results.
          </div>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`chat-msg ${m.role}`}>
            {m.status ? (
              <span className="chat-status">
                <span className="refetch-dot" /> {m.status}
              </span>
            ) : (
              <>
                <div className="chat-text">{m.text}</div>
                {m.reportId && (
                  <div className="chat-downloads">
                    <a className="btn" href={reportDownloadUrl(`/api/reports/${m.reportId}.pdf`)} target="_blank" rel="noreferrer">PDF</a>
                    <a className="btn-ghost" href={reportDownloadUrl(`/api/reports/${m.reportId}.md`)} target="_blank" rel="noreferrer">Markdown</a>
                  </div>
                )}
                {m.chart && <InlineChart spec={m.chart.spec} data={m.chart.data} />}
                {m.sql && (
                  <details className="chat-sql">
                    <summary>SQL</summary>
                    <pre>{m.sql}</pre>
                  </details>
                )}
              </>
            )}
          </div>
        ))}
      </div>

      <form className="chat-input" onSubmit={submit}>
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={busy ? "Working…" : "Ask a question…"}
          disabled={busy}
          aria-label="Chat message"
        />
        <button className="btn" type="submit" disabled={busy || !draft.trim()}>
          Send
        </button>
      </form>
    </aside>
  );
}

export function ChatToggle({ onClick }: { onClick: () => void }) {
  return (
    <button className="chat-toggle" onClick={onClick} title="Open AI chat">
      💬 Ask the data
    </button>
  );
}
