import { type ReactNode, useEffect, useRef } from "react";
import type { ChatMessage } from "../../hooks/useChatStream";
import type { DatasetSummary } from "../../types/api";
import { Composer } from "./Composer";
import { MessageView } from "./MessageView";

interface Props {
  dataset: DatasetSummary | null;
  messages: ChatMessage[];
  streaming: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
  footer: ReactNode;
}

const SAMPLE_SUGGESTIONS = [
  "What are the top 5 product categories by revenue?",
  "Show monthly revenue as a chart",
  "Which countries have the most customers?",
  "What share of orders were cancelled or refunded?",
];
const GENERIC_SUGGESTIONS = [
  "Give me an overview of this data",
  "How many rows are in each table?",
  "What are the most common values in the main text column?",
];

export function ChatPanel({ dataset, messages, streaming, onSend, onStop, footer }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickRef = useRef(true);
  const last = messages[messages.length - 1];
  const tick = last ? last.content.length + last.tables.length + (last.chart ? 1 : 0) : 0;

  // biome-ignore lint/correctness/useExhaustiveDependencies: scroll as the streamed answer grows
  useEffect(() => {
    const el = scrollRef.current;
    if (el && stickRef.current) el.scrollTop = el.scrollHeight;
  }, [tick, messages.length]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (el) stickRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
  };

  const isSample = dataset?.tables.some((t) => t.name === "order_items") ?? false;
  const suggestions = isSample ? SAMPLE_SUGGESTIONS : GENERIC_SUGGESTIONS;
  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div ref={scrollRef} onScroll={onScroll} className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl space-y-6 px-4 py-6">
          {messages.length === 0 ? (
            <div className="pt-10 text-center">
              <h2 className="text-2xl font-semibold">
                {dataset ? `Ask anything about ${dataset.name}` : "Ask your data"}
              </h2>
              <p className="mt-2 text-sm text-muted">
                I write SQL, run it read-only against your tables, and answer with text, tables and
                charts.
              </p>
              {dataset && (
                <div className="mt-6 grid gap-2 sm:grid-cols-2">
                  {suggestions.map((s) => (
                    <button
                      key={s}
                      type="button"
                      onClick={() => onSend(s)}
                      disabled={streaming}
                      className="rounded-xl border border-line bg-card px-4 py-3 text-left text-sm hover:border-accent disabled:opacity-50"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ) : (
            messages.map((m) => (
              <MessageView
                key={m.id}
                message={m}
                canRetry={!streaming && m === lastAssistant && m.status !== "streaming"}
                onRetry={onSend}
              />
            ))
          )}
        </div>
      </div>
      <Composer
        streaming={streaming}
        disabled={!dataset}
        onSend={onSend}
        onStop={onStop}
        footer={footer}
      />
    </div>
  );
}
