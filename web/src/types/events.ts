export type Step = "reading_schema" | "writing_sql" | "running_query" | "analysing";
export type AnswerFormat = "text" | "table" | "chart" | "mixed";
export type Cell = string | number | boolean | null;

export interface QueryItem {
  title: string;
  sql: string;
}

export interface ChartSpec {
  type: "bar" | "line" | "area" | "pie" | "scatter";
  title: string;
  table_id: string;
  x: string;
  y: string[];
  series: string | null;
  x_label: string | null;
  y_label: string | null;
}

export type GateMode = "byok" | "free" | "blocked";

export interface GateInfo {
  mode: GateMode;
  remaining: number | null;
}

/** Mirrors the SSE protocol documented in CLAUDE.md. Discriminated on `type`. */
export type StreamEvent =
  | { type: "init"; conversation_id: string; message_id: string }
  | { type: "status"; step: Step }
  | { type: "title"; title: string }
  | { type: "sql"; queries: QueryItem[]; cache_hit: boolean; answer_format: AnswerFormat }
  | {
      type: "table";
      table_id: string;
      title: string;
      columns: string[];
      rows: Cell[][];
      truncated: boolean;
    }
  | { type: "chart"; spec: ChartSpec }
  | { type: "analysis_token"; token: string }
  | { type: "error"; code: string; message: string }
  | { type: "done"; gate: GateInfo };
