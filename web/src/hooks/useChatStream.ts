import { useCallback, useEffect, useRef, useState } from "react";
import { API_URL, API_URL_MISSING, ApiError, api, buildHeaders } from "../lib/api";
import type { MessageStatus, StoredMessage, TableData } from "../types/api";
import type {
  AnswerFormat,
  ChartSpec,
  GateInfo,
  QueryItem,
  Step,
  StreamEvent,
} from "../types/events";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  status: MessageStatus;
  step?: Step;
  sql?: { queries: QueryItem[]; cache_hit: boolean; answer_format: AnswerFormat };
  tables: TableData[];
  chart?: ChartSpec;
  error?: { code: string; message: string };
  question?: string;
}

interface Options {
  onGate: (gate: GateInfo) => void;
  onNeedKey: (code: string, message: string) => void;
  onTitle?: (title: string) => void;
}

function fromStored(m: StoredMessage): ChatMessage {
  const interrupted = m.status === "streaming"; // server died / reload mid-stream
  return {
    id: m.id,
    role: m.role,
    content: m.content,
    status: interrupted ? "cancelled" : m.status,
    sql: m.sql ?? undefined,
    tables: m.tables ?? [],
    chart: m.chart ?? undefined,
    error: m.status === "failed" ? { code: "internal", message: m.content } : undefined,
  };
}

/** Parse an SSE byte stream into events (`data: {json}` blocks separated by blank lines). */
async function* readEvents(body: ReadableStream<Uint8Array>): AsyncGenerator<StreamEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const block = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const data = block
          .split("\n")
          .filter((l) => l.startsWith("data:"))
          .map((l) => l.slice(5).trimStart())
          .join("\n");
        if (data) {
          try {
            yield JSON.parse(data) as StreamEvent;
          } catch {
            // ignore malformed event
          }
        }
        boundary = buffer.indexOf("\n\n");
      }
    }
  } finally {
    reader.releaseLock();
  }
}

export function useChatStream({ onGate, onNeedKey, onTitle }: Options) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [title, setTitle] = useState<string | null>(null);
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const convRef = useRef<string | null>(null);
  const callbacks = useRef({ onGate, onNeedKey, onTitle });
  callbacks.current = { onGate, onNeedKey, onTitle };

  const patchAssistant = useCallback((id: string, patch: (m: ChatMessage) => ChatMessage) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? patch(m) : m)));
  }, []);

  const send = useCallback(
    async (question: string) => {
      const text = question.trim();
      if (!text || abortRef.current) return;
      const tempId = `local-${crypto.randomUUID()}`;
      const assistantId = `${tempId}-a`;
      setMessages((prev) => [
        ...prev,
        { id: tempId, role: "user", content: text, status: "completed", tables: [] },
        {
          id: assistantId,
          role: "assistant",
          content: "",
          status: "streaming",
          tables: [],
          question: text,
        },
      ]);
      const controller = new AbortController();
      abortRef.current = controller;
      setStreaming(true);

      const fail = (code: string, message: string) => {
        patchAssistant(assistantId, (m) => ({
          ...m,
          status: "failed",
          step: undefined,
          error: { code, message },
        }));
        if (code === "blocked" || code === "quota_exhausted" || code === "invalid_key") {
          callbacks.current.onNeedKey(code, message);
        }
      };

      try {
        if (API_URL_MISSING) throw new ApiError("VITE_API_URL is not set for this deployment.", 0);
        const res = await fetch(`${API_URL}/api/chat/stream`, {
          method: "POST",
          headers: buildHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({ question: text, conversation_id: convRef.current }),
          signal: controller.signal,
        });
        if (!res.ok || !res.body) {
          let detail = `Request failed (${res.status})`;
          try {
            const body = await res.json();
            if (typeof body.detail === "string") detail = body.detail;
          } catch {
            // ignore
          }
          fail("internal", detail);
          return;
        }
        let finished = false;
        for await (const ev of readEvents(res.body)) {
          switch (ev.type) {
            case "init":
              convRef.current = ev.conversation_id;
              setConversationId(ev.conversation_id);
              break;
            case "status":
              patchAssistant(assistantId, (m) => ({ ...m, step: ev.step }));
              break;
            case "title":
              setTitle(ev.title);
              callbacks.current.onTitle?.(ev.title);
              break;
            case "sql":
              patchAssistant(assistantId, (m) => ({
                ...m,
                sql: {
                  queries: ev.queries,
                  cache_hit: ev.cache_hit,
                  answer_format: ev.answer_format,
                },
              }));
              break;
            case "table":
              patchAssistant(assistantId, (m) => ({
                ...m,
                tables: [
                  ...m.tables,
                  {
                    table_id: ev.table_id,
                    title: ev.title,
                    columns: ev.columns,
                    rows: ev.rows,
                    truncated: ev.truncated,
                  },
                ],
              }));
              break;
            case "chart":
              patchAssistant(assistantId, (m) => ({ ...m, chart: ev.spec }));
              break;
            case "analysis_token":
              patchAssistant(assistantId, (m) => ({ ...m, content: m.content + ev.token }));
              break;
            case "error":
              finished = true;
              fail(ev.code, ev.message);
              if (ev.code === "blocked") {
                callbacks.current.onGate({ mode: "blocked", remaining: 0 });
              }
              break;
            case "done":
              finished = true;
              patchAssistant(assistantId, (m) => ({ ...m, status: "completed", step: undefined }));
              callbacks.current.onGate(ev.gate);
              break;
          }
        }
        if (!finished) {
          patchAssistant(assistantId, (m) =>
            m.status === "streaming" ? { ...m, status: "cancelled", step: undefined } : m,
          );
        }
      } catch (e) {
        if (controller.signal.aborted) {
          patchAssistant(assistantId, (m) => ({ ...m, status: "cancelled", step: undefined }));
        } else {
          fail("internal", e instanceof ApiError ? e.message : "The connection was interrupted.");
        }
      } finally {
        abortRef.current = null;
        setStreaming(false);
      }
    },
    [patchAssistant],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    convRef.current = null;
    setConversationId(null);
    setMessages([]);
    setTitle(null);
  }, []);

  /** Restore the most recent conversation (after a page reload). */
  const restoreLatest = useCallback(async () => {
    try {
      const { conversations } = await api.listConversations();
      const latest = conversations[0];
      if (!latest) return;
      const { messages: stored } = await api.getMessages(latest.id);
      convRef.current = latest.id;
      setConversationId(latest.id);
      setTitle(latest.title);
      setMessages(stored.map(fromStored));
    } catch {
      // nothing to restore
    }
  }, []);

  useEffect(() => () => abortRef.current?.abort(), []);

  return { messages, conversationId, title, streaming, send, stop, reset, restoreLatest };
}
