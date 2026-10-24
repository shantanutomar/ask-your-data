import { lazy, Suspense, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage } from "../../hooks/useChatStream";
import { ResultTable } from "./ResultTable";
import { SqlBlock } from "./SqlBlock";
import { StatusLine } from "./StatusLine";

const ChartView = lazy(() => import("../charts/ChartView").then((m) => ({ default: m.ChartView })));

interface Props {
  message: ChatMessage;
  canRetry: boolean;
  onRetry: (question: string) => void;
}

export function MessageView({ message, canRetry, onRetry }: Props) {
  const [copied, setCopied] = useState(false);

  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl bg-panel px-4 py-2.5 text-[15px] leading-relaxed">
          {message.content}
        </div>
      </div>
    );
  }

  const streaming = message.status === "streaming";
  const chartTable = message.chart
    ? message.tables.find((t) => t.table_id === message.chart?.table_id)
    : undefined;
  const hasAnswer = message.content.length > 0;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard unavailable
    }
  };

  return (
    <div className="text-[15px]">
      {streaming && !hasAnswer && <StatusLine step={message.step} />}
      {streaming && hasAnswer && message.step && message.step !== "analysing" && (
        <StatusLine step={message.step} />
      )}

      {hasAnswer && message.status !== "failed" && (
        <div className={`prose-answer ${streaming ? "caret" : ""}`}>
          <Markdown remarkPlugins={[remarkGfm]}>{message.content}</Markdown>
        </div>
      )}

      {message.tables.length > 0 &&
        (message.chart ? (
          <details className="my-3 text-sm">
            <summary className="cursor-pointer select-none text-muted hover:text-ink">
              View data
            </summary>
            {message.tables.map((t) => (
              <ResultTable key={t.table_id} table={t} />
            ))}
          </details>
        ) : (
          message.tables.map((t) => <ResultTable key={t.table_id} table={t} />)
        ))}

      {message.chart && (
        <Suspense fallback={<div className="my-3 h-80 rounded-lg border border-line" />}>
          <ChartView spec={message.chart} table={chartTable} />
        </Suspense>
      )}

      {message.sql && <SqlBlock queries={message.sql.queries} cacheHit={message.sql.cache_hit} />}

      {message.status === "failed" && message.error && (
        <p
          role="alert"
          className="rounded-lg border border-danger/40 px-3 py-2 text-sm text-danger"
        >
          {message.error.message}
        </p>
      )}
      {message.status === "cancelled" && (
        <p className="text-sm italic text-muted">
          Stopped{hasAnswer ? "" : " before an answer was produced"}.
        </p>
      )}

      {!streaming && (
        <div className="mt-2 flex gap-3 text-xs text-muted">
          {hasAnswer && message.status === "completed" && (
            <button type="button" onClick={() => void copy()} className="hover:text-ink">
              {copied ? "Copied" : "Copy"}
            </button>
          )}
          {canRetry && message.question && (
            <button
              type="button"
              onClick={() => onRetry(message.question as string)}
              className="hover:text-ink"
            >
              Retry
            </button>
          )}
        </div>
      )}
    </div>
  );
}
