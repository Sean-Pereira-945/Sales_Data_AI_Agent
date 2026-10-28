import { useCallback, useRef, useState } from "react";
import { streamChat } from "../api/chat";
import { getJson } from "../api/client";
import { filtersToParams, useFilters } from "../state/filters";
import type { ChartSpec, SummaryResponse } from "../api/types";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  status?: string;                 // transient "running query…" while streaming
  sql?: string | null;
  chart?: { spec: ChartSpec; data: Record<string, unknown>[] } | null;
}

let _seq = 0;
const nextId = () => `m${++_seq}`;

export function useChat() {
  const { filters } = useFilters();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const threadId = useRef<string | null>(null);

  const patchLast = useCallback((patch: Partial<ChatMessage>) => {
    setMessages((prev) => {
      if (!prev.length) return prev;
      const copy = prev.slice();
      copy[copy.length - 1] = { ...copy[copy.length - 1], ...patch };
      return copy;
    });
  }, []);

  const send = useCallback(
    async (text: string) => {
      if (!text.trim() || busy) return;
      setBusy(true);
      setMessages((prev) => [
        ...prev,
        { id: nextId(), role: "user", text },
        { id: nextId(), role: "assistant", text: "", status: "thinking…" },
      ]);
      await streamChat(text, threadId.current, {
        onStatus: (stage) => patchLast({ status: `${stage}…` }),
        onFinal: (f) => {
          threadId.current = f.thread_id;
          patchLast({
            status: undefined,
            text: f.insight || "(no answer)",
            sql: f.sql,
            chart: f.chart_spec && f.data?.length ? { spec: f.chart_spec, data: f.data } : null,
          });
        },
        onError: (m) => patchLast({ status: undefined, text: `⚠️ ${m}` }),
      });
      setBusy(false);
    },
    [busy, patchLast],
  );

  /** "Summarize dashboard" — appends the brief as an assistant message. */
  const summarize = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    setMessages((prev) => [
      ...prev,
      { id: nextId(), role: "user", text: "Summarize the dashboard (current filters)." },
      { id: nextId(), role: "assistant", text: "", status: "summarizing…" },
    ]);
    try {
      const res = await getJson<SummaryResponse>("/api/insights/summary", filtersToParams(filters));
      patchLast({ status: undefined, text: res.summary });
    } catch (e) {
      patchLast({ status: undefined, text: `⚠️ ${e instanceof Error ? e.message : "error"}` });
    }
    setBusy(false);
  }, [busy, filters, patchLast]);

  return { messages, busy, send, summarize };
}
