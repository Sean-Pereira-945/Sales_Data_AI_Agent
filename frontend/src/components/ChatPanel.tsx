import { useState } from "react";

/**
 * Side chat panel — placeholder for Phase 4 (LangGraph agent with streaming +
 * thread memory). The input is disabled; it exists to lock in the layout.
 */
export function ChatPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <aside className={open ? "chat open" : "chat"} aria-label="AI chat panel">
      <header className="chat-head">
        <span>Ask the data</span>
        <button className="btn-ghost" onClick={onClose} aria-label="Close chat">
          ✕
        </button>
      </header>
      <div className="chat-body">
        <div className="chat-msg assistant">
          Hi! Once the agent is wired up (Phase 4), you’ll be able to ask things like
          <em> “GMV trend for the South region in 2018”</em> or <em>“which categories have the worst reviews?”</em>
          and get answers, charts, and reports — grounded only in aggregated query results.
        </div>
      </div>
      <form
        className="chat-input"
        onSubmit={(e) => e.preventDefault()}
      >
        <input placeholder="Chat coming in Phase 4…" disabled />
        <button className="btn" type="submit" disabled>
          Send
        </button>
      </form>
    </aside>
  );
}

export function ChatToggle({ onClick }: { onClick: () => void }) {
  const [hovered, setHovered] = useState(false);
  return (
    <button
      className="chat-toggle"
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      title="Open AI chat"
    >
      💬 {hovered ? "Ask the data" : "Chat"}
    </button>
  );
}
