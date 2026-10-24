import { useMemo, useState } from "react";
import {
  COLUMN_TYPES,
  type ColumnType,
  type CommitTable,
  type DraftPreview,
} from "../../types/api";
import type { Cell } from "../../types/events";

interface EditColumn {
  source: string;
  index: number;
  name: string;
  type: ColumnType;
  keep: boolean;
}

interface EditTable {
  source: string;
  name: string;
  keep: boolean;
  rowCount: number;
  columns: EditColumn[];
  sampleRows: Cell[][];
}

interface Props {
  preview: DraftPreview;
  busy: boolean;
  error: string | null;
  onBack: () => void;
  onCommit: (name: string, tables: CommitTable[]) => void;
}

function initial(preview: DraftPreview): EditTable[] {
  return preview.tables.map((t) => ({
    source: t.name,
    name: t.name,
    keep: true,
    rowCount: t.row_count,
    sampleRows: t.sample_rows,
    columns: t.columns.map((c, index) => ({
      source: c.name,
      index,
      name: c.name,
      type: c.type,
      keep: true,
    })),
  }));
}

export function PreviewEditor({ preview, busy, error, onBack, onCommit }: Props) {
  const [name, setName] = useState(preview.name);
  const [tables, setTables] = useState<EditTable[]>(() => initial(preview));

  const updateTable = (i: number, patch: Partial<EditTable>) =>
    setTables((prev) => prev.map((t, k) => (k === i ? { ...t, ...patch } : t)));
  const updateColumn = (ti: number, ci: number, patch: Partial<EditColumn>) =>
    setTables((prev) =>
      prev.map((t, k) =>
        k === ti
          ? { ...t, columns: t.columns.map((c, j) => (j === ci ? { ...c, ...patch } : c)) }
          : t,
      ),
    );

  const valid = useMemo(() => {
    const kept = tables.filter((t) => t.keep);
    return (
      kept.length > 0 &&
      kept.every(
        (t) =>
          t.name.trim() &&
          t.columns.some((c) => c.keep) &&
          t.columns.every((c) => !c.keep || c.name.trim()),
      )
    );
  }, [tables]);

  const submit = () => {
    const payload: CommitTable[] = tables
      .filter((t) => t.keep)
      .map((t) => ({
        source: t.source,
        name: t.name.trim(),
        columns: t.columns
          .filter((c) => c.keep)
          .map((c) => ({ source: c.source, name: c.name.trim(), type: c.type })),
      }));
    onCommit(name.trim() || preview.name, payload);
  };

  return (
    <div className="space-y-5">
      <p className="text-sm text-muted">
        Check how your data was read. Rename tables and columns, fix column types, or drop what you
        don't need. Names are converted to snake_case.
      </p>
      <div>
        <label htmlFor="dataset-name" className="mb-1 block text-xs font-medium">
          Dataset name
        </label>
        <input
          id="dataset-name"
          value={name}
          maxLength={80}
          onChange={(e) => setName(e.target.value)}
          className="w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm outline-none focus:border-accent"
        />
      </div>

      {tables.map((t, ti) => {
        const keptCols = t.columns.filter((c) => c.keep);
        return (
          <section
            key={t.source}
            className={`rounded-xl border border-line ${t.keep ? "" : "opacity-50"}`}
          >
            <div className="flex flex-wrap items-center gap-3 border-b border-line px-3 py-2">
              <input
                type="checkbox"
                checked={t.keep}
                onChange={(e) => updateTable(ti, { keep: e.target.checked })}
                aria-label={`Include table ${t.source}`}
              />
              <input
                value={t.name}
                onChange={(e) => updateTable(ti, { name: e.target.value })}
                aria-label={`Name of table ${t.source}`}
                className="min-w-0 flex-1 rounded-md border border-line bg-bg px-2 py-1 text-sm font-medium outline-none focus:border-accent"
              />
              <span className="text-xs text-muted">{t.rowCount.toLocaleString()} rows</span>
            </div>

            <div className="grid gap-1 px-3 py-2">
              {t.columns.map((c, ci) => (
                <div
                  key={c.source}
                  className={`flex items-center gap-2 ${c.keep ? "" : "opacity-50"}`}
                >
                  <input
                    type="checkbox"
                    checked={c.keep}
                    onChange={(e) => updateColumn(ti, ci, { keep: e.target.checked })}
                    aria-label={`Include column ${c.source}`}
                  />
                  <input
                    value={c.name}
                    onChange={(e) => updateColumn(ti, ci, { name: e.target.value })}
                    aria-label={`Name of column ${c.source}`}
                    className="min-w-0 flex-1 rounded-md border border-line bg-bg px-2 py-1 text-sm outline-none focus:border-accent"
                  />
                  <select
                    value={c.type}
                    onChange={(e) => updateColumn(ti, ci, { type: e.target.value as ColumnType })}
                    aria-label={`Type of column ${c.source}`}
                    className="rounded-md border border-line bg-bg px-2 py-1 text-sm"
                  >
                    {COLUMN_TYPES.map((ct) => (
                      <option key={ct} value={ct}>
                        {ct}
                      </option>
                    ))}
                  </select>
                </div>
              ))}
            </div>

            {keptCols.length > 0 && (
              <div className="overflow-x-auto border-t border-line">
                <table className="w-full border-collapse text-xs">
                  <thead className="bg-panel">
                    <tr>
                      {keptCols.map((c) => (
                        <th
                          key={c.source}
                          className="whitespace-nowrap px-2 py-1 text-left font-medium"
                        >
                          {c.name}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {t.sampleRows.map((row, r) => (
                      // biome-ignore lint/suspicious/noArrayIndexKey: sample rows have no identity
                      <tr key={r} className="border-t border-line">
                        {keptCols.map((c) => (
                          <td key={c.source} className="whitespace-nowrap px-2 py-1">
                            {row[c.index] === null || row[c.index] === undefined ? (
                              <span className="text-muted">—</span>
                            ) : (
                              String(row[c.index])
                            )}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        );
      })}

      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onBack}
          disabled={busy}
          className="rounded-lg px-3 py-2 text-sm text-muted hover:bg-panel"
        >
          Back
        </button>
        <button
          type="button"
          onClick={submit}
          disabled={busy || !valid}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-ink disabled:opacity-50"
        >
          {busy ? "Loading data…" : "Load data"}
        </button>
      </div>
    </div>
  );
}
