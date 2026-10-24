import { useState } from "react";
import type { QueryItem } from "../../types/events";

interface Props {
  queries: QueryItem[];
  cacheHit: boolean;
}

export function SqlBlock({ queries, cacheHit }: Props) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(queries.map((q) => q.sql).join("\n\n"));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard unavailable
    }
  };
  return (
    <details className="my-3 rounded-lg border border-line bg-card text-sm">
      <summary className="cursor-pointer select-none px-3 py-2 text-muted hover:text-ink">
        SQL used
        {cacheHit && <span className="ml-2 rounded bg-panel px-1.5 py-0.5 text-xs">cached</span>}
      </summary>
      <div className="space-y-3 border-t border-line px-3 py-3">
        {queries.map((q, i) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: queries have no identity
          <div key={i}>
            <div className="mb-1 text-xs font-medium text-muted">{q.title}</div>
            <pre className="overflow-x-auto rounded-md bg-panel p-3 font-mono text-xs leading-relaxed">
              {q.sql}
            </pre>
          </div>
        ))}
        <button
          type="button"
          onClick={() => void copy()}
          className="text-xs text-muted underline hover:text-ink"
        >
          {copied ? "Copied" : "Copy SQL"}
        </button>
      </div>
    </details>
  );
}
