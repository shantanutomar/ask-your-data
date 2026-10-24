import type { DatasetSummary } from "../../types/api";

interface Props {
  dataset: DatasetSummary | null;
  busy: boolean;
  onUpload: () => void;
  onSample: () => void;
  onReset: () => void;
}

function hoursLeft(iso: string): string {
  const ms = new Date(iso).getTime() - Date.now();
  if (ms <= 0) return "expired";
  const h = Math.floor(ms / 3_600_000);
  return h >= 1 ? `${h}h left` : `${Math.max(1, Math.round(ms / 60_000))}m left`;
}

export function DatasetPanel({ dataset, busy, onUpload, onSample, onReset }: Props) {
  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-line px-4 py-3">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted">Dataset</h2>
        {dataset ? (
          <div className="mt-1">
            <div className="truncate font-medium">{dataset.name}</div>
            <div className="text-xs text-muted">
              Auto-deletes in {hoursLeft(dataset.expires_at)}
            </div>
          </div>
        ) : (
          <p className="mt-1 text-sm text-muted">No data yet.</p>
        )}
      </div>

      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto px-3 py-3">
        {dataset?.tables.map((t) => (
          <details
            key={t.name}
            className="rounded-lg border border-line bg-card text-sm"
            open={dataset.tables.length <= 2}
          >
            <summary className="flex cursor-pointer select-none items-baseline justify-between gap-2 px-3 py-2">
              <span className="truncate font-medium">{t.name}</span>
              <span className="shrink-0 text-xs text-muted">
                {t.row_count.toLocaleString()} rows
              </span>
            </summary>
            <ul className="border-t border-line px-3 py-2">
              {t.columns.map((c) => (
                <li key={c.name} className="flex justify-between gap-2 py-0.5 text-xs">
                  <span className="truncate">{c.name}</span>
                  <span className="text-muted">{c.type}</span>
                </li>
              ))}
            </ul>
          </details>
        ))}
      </div>

      <div className="space-y-2 border-t border-line p-3">
        <button
          type="button"
          onClick={onUpload}
          disabled={busy}
          className="w-full rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-ink disabled:opacity-50"
        >
          {dataset ? "Replace data…" : "Upload or paste data…"}
        </button>
        <button
          type="button"
          onClick={onSample}
          disabled={busy}
          className="w-full rounded-lg border border-line px-3 py-2 text-sm hover:bg-card disabled:opacity-50"
        >
          Load sample dataset
        </button>
        {dataset && (
          <button
            type="button"
            onClick={onReset}
            disabled={busy}
            className="w-full rounded-lg px-3 py-2 text-sm text-danger hover:bg-card disabled:opacity-50"
          >
            Reset
          </button>
        )}
      </div>
    </div>
  );
}
