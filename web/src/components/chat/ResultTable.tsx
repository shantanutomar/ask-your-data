import type { TableData } from "../../types/api";
import type { Cell } from "../../types/events";

const numberFormat = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 });

function renderCell(value: Cell) {
  if (value === null) return <span className="text-muted">—</span>;
  if (typeof value === "number")
    return Number.isInteger(value) ? String(value) : numberFormat.format(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  return value;
}

export function ResultTable({ table }: { table: TableData }) {
  return (
    <figure className="my-3">
      <figcaption className="mb-1 flex items-baseline justify-between text-xs text-muted">
        <span className="font-medium text-ink">{table.title}</span>
        <span>
          {table.rows.length} {table.rows.length === 1 ? "row" : "rows"}
        </span>
      </figcaption>
      <div className="max-h-96 overflow-auto rounded-lg border border-line bg-card">
        <table className="w-full border-collapse text-sm">
          <thead className="sticky top-0 bg-panel">
            <tr>
              {table.columns.map((c, i) => (
                <th
                  // biome-ignore lint/suspicious/noArrayIndexKey: columns can repeat names
                  key={`${c}-${i}`}
                  className="whitespace-nowrap border-b border-line px-3 py-2 text-left font-medium"
                >
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, r) => (
              // biome-ignore lint/suspicious/noArrayIndexKey: rows have no identity
              <tr key={r} className="border-b border-line last:border-0">
                {row.map((cell, c) => (
                  <td
                    // biome-ignore lint/suspicious/noArrayIndexKey: cells have no identity
                    key={c}
                    className={`whitespace-nowrap px-3 py-1.5 ${typeof cell === "number" ? "text-right tabular-nums" : ""}`}
                  >
                    {renderCell(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {table.truncated && (
        <p className="mt-1 text-xs text-muted">
          Showing the first {table.rows.length} rows; more rows matched.
        </p>
      )}
    </figure>
  );
}
