import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  Pie,
  Cell as PieCell,
  PieChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { TableData } from "../../types/api";
import type { ChartSpec } from "../../types/events";

const COLORS = Array.from({ length: 8 }, (_, i) => `var(--chart-${i + 1})`);
const HEIGHT = 320;

type Row = Record<string, string | number | null>;

function toNumber(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

/** Build recharts rows from a result table. A `series` column is pivoted into one key per value. */
function prepare(spec: ChartSpec, table: TableData): { data: Row[]; keys: string[] } {
  const xi = table.columns.indexOf(spec.x);
  const yIdx = spec.y.map((y) => table.columns.indexOf(y));
  if (xi < 0 || yIdx.some((i) => i < 0)) return { data: [], keys: [] };

  const seriesIdx = spec.series ? table.columns.indexOf(spec.series) : -1;
  if (seriesIdx >= 0 && yIdx[0] !== undefined) {
    const y0 = yIdx[0];
    const keys: string[] = [];
    const byX = new Map<string, Row>();
    for (const row of table.rows) {
      const xKey = String(row[xi] ?? "");
      const sKey = String(row[seriesIdx] ?? "—");
      if (!keys.includes(sKey)) keys.push(sKey);
      const entry = byX.get(xKey) ?? { [spec.x]: xKey };
      entry[sKey] = toNumber(row[y0]);
      byX.set(xKey, entry);
    }
    return { data: [...byX.values()], keys };
  }

  const data = table.rows.map((row) => {
    const entry: Row = { [spec.x]: row[xi] === null ? null : String(row[xi]) };
    yIdx.forEach((i, k) => {
      entry[spec.y[k] as string] = toNumber(row[i]);
    });
    return entry;
  });
  return { data, keys: spec.y };
}

const axisProps = {
  tick: { fill: "var(--muted)", fontSize: 12 },
  stroke: "var(--line)",
};

export function ChartView({ spec, table }: { spec: ChartSpec; table: TableData | undefined }) {
  if (!table) return null;
  const { data, keys } = prepare(spec, table);
  if (data.length === 0) return null;

  const xLabel = spec.x_label
    ? { value: spec.x_label, position: "insideBottom" as const, offset: -4 }
    : undefined;
  const yLabel = spec.y_label
    ? { value: spec.y_label, angle: -90, position: "insideLeft" as const }
    : undefined;
  const common = { data, margin: { top: 8, right: 16, bottom: xLabel ? 20 : 4, left: 4 } };
  const tooltip = (
    <Tooltip
      contentStyle={{
        background: "var(--card)",
        border: "1px solid var(--line)",
        borderRadius: 8,
        color: "var(--ink)",
      }}
    />
  );
  const legend = keys.length > 1 ? <Legend /> : null;
  const grid = <CartesianGrid stroke="var(--line)" strokeDasharray="3 3" />;
  const xAxis = <XAxis dataKey={spec.x} label={xLabel} {...axisProps} />;
  const yAxis = <YAxis label={yLabel} width={yLabel ? 84 : 60} {...axisProps} />;

  let chart: React.ReactElement;
  if (spec.type === "bar") {
    chart = (
      <BarChart {...common}>
        {grid}
        {xAxis}
        {yAxis}
        {tooltip}
        {legend}
        {keys.map((k, i) => (
          <Bar key={k} dataKey={k} fill={COLORS[i % COLORS.length]} radius={[3, 3, 0, 0]} />
        ))}
      </BarChart>
    );
  } else if (spec.type === "line") {
    chart = (
      <LineChart {...common}>
        {grid}
        {xAxis}
        {yAxis}
        {tooltip}
        {legend}
        {keys.map((k, i) => (
          <Line
            key={k}
            dataKey={k}
            stroke={COLORS[i % COLORS.length]}
            strokeWidth={2}
            dot={data.length < 40}
          />
        ))}
      </LineChart>
    );
  } else if (spec.type === "area") {
    chart = (
      <AreaChart {...common}>
        {grid}
        {xAxis}
        {yAxis}
        {tooltip}
        {legend}
        {keys.map((k, i) => (
          <Area
            key={k}
            dataKey={k}
            stroke={COLORS[i % COLORS.length]}
            fill={COLORS[i % COLORS.length]}
            fillOpacity={0.25}
          />
        ))}
      </AreaChart>
    );
  } else if (spec.type === "pie") {
    const yKey = keys[0] ?? spec.y[0] ?? "";
    chart = (
      <PieChart>
        {tooltip}
        <Legend />
        <Pie data={data} dataKey={yKey} nameKey={spec.x} outerRadius={110} label>
          {data.map((row, i) => (
            <PieCell key={String(row[spec.x])} fill={COLORS[i % COLORS.length]} />
          ))}
        </Pie>
      </PieChart>
    );
  } else {
    const yKey = spec.y[0] ?? "";
    const numeric = table.rows
      .map((r) => ({
        x: toNumber(r[table.columns.indexOf(spec.x)]),
        y: toNumber(r[table.columns.indexOf(yKey)]),
      }))
      .filter((p): p is { x: number; y: number } => p.x !== null && p.y !== null);
    chart = (
      <ScatterChart margin={common.margin}>
        {grid}
        <XAxis dataKey="x" type="number" name={spec.x} label={xLabel} {...axisProps} />
        <YAxis
          dataKey="y"
          type="number"
          name={yKey}
          label={yLabel}
          width={yLabel ? 84 : 60}
          {...axisProps}
        />
        {tooltip}
        <Scatter data={numeric} fill={COLORS[0]} />
      </ScatterChart>
    );
  }

  return (
    <figure className="my-3 rounded-lg border border-line bg-card p-3">
      <figcaption className="mb-2 text-sm font-medium">{spec.title}</figcaption>
      <ResponsiveContainer width="100%" height={HEIGHT}>
        {chart}
      </ResponsiveContainer>
    </figure>
  );
}
