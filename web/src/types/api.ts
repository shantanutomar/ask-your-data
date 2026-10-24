import type { AnswerFormat, Cell, ChartSpec, QueryItem } from "./events";

export type ColumnType = "text" | "integer" | "numeric" | "boolean" | "date" | "timestamp";
export const COLUMN_TYPES: ColumnType[] = [
  "text",
  "integer",
  "numeric",
  "boolean",
  "date",
  "timestamp",
];

export interface DatasetColumn {
  name: string;
  type: ColumnType;
}

export interface DatasetTable {
  name: string;
  row_count: number;
  columns: DatasetColumn[];
}

export interface DatasetSummary {
  id: string;
  name: string;
  expires_at: string;
  tables: DatasetTable[];
}

export interface DraftTablePreview {
  name: string;
  row_count: number;
  columns: DatasetColumn[];
  sample_rows: Cell[][];
}

export interface DraftPreview {
  draft_id: string;
  name: string;
  tables: DraftTablePreview[];
}

export interface CommitTable {
  source: string;
  name: string;
  columns: { source: string; name: string; type: ColumnType }[];
}

export interface TableData {
  table_id: string;
  title: string;
  columns: string[];
  rows: Cell[][];
  truncated: boolean;
}

export type MessageStatus = "streaming" | "completed" | "cancelled" | "failed";

export interface StoredMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sql: { queries: QueryItem[]; cache_hit: boolean; answer_format: AnswerFormat } | null;
  tables: TableData[] | null;
  chart: ChartSpec | null;
  status: MessageStatus;
}

export interface ConversationSummary {
  id: string;
  title: string | null;
  updated_at: string;
}
