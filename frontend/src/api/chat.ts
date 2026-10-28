import type { ChatFinal } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

export interface ChatHandlers {
  onStatus: (stage: string) => void;
  onFinal: (f: ChatFinal) => void;
  onError: (message: string) => void;
}

/** POST a chat message and consume the SSE stream (status events → final). */
export async function streamChat(
  message: string,
  threadId: string | null,
  h: ChatHandlers,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, thread_id: threadId }),
    });
  } catch (e) {
    h.onError(e instanceof Error ? e.message : "network error");
    return;
  }
  if (!res.ok || !res.body) {
    h.onError(`HTTP ${res.status}`);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const frames = buf.split("\n\n");
    buf = frames.pop() ?? "";
    for (const frame of frames) {
      const line = frame.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;
      let evt: { type: string; stage?: string; message?: string };
      try {
        evt = JSON.parse(line.slice(6));
      } catch {
        continue;
      }
      if (evt.type === "status" && evt.stage) h.onStatus(evt.stage);
      else if (evt.type === "final") h.onFinal(evt as unknown as ChatFinal);
      else if (evt.type === "error") h.onError(evt.message ?? "error");
    }
  }
}
