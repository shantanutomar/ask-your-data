import type {
  CommitTable,
  ConversationSummary,
  DatasetSummary,
  DraftPreview,
  StoredMessage,
} from "../types/api";
import type { GateInfo } from "../types/events";
import { getUserKey } from "./userKey";
import { getVisitorId } from "./visitor";

// Local dev falls back to the default API port; a production build must set VITE_API_URL.
const configuredUrl: string | undefined =
  import.meta.env.VITE_API_URL || (import.meta.env.DEV ? "http://localhost:8000" : undefined);
export const API_URL = (configuredUrl ?? "").replace(/\/$/, "");
export const API_URL_MISSING = !configuredUrl;

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
  ) {
    super(message);
  }
}

export function buildHeaders(extra?: Record<string, string>): Record<string, string> {
  const headers: Record<string, string> = { "X-Visitor-Id": getVisitorId(), ...extra };
  const key = getUserKey();
  if (key) headers["X-User-Api-Key"] = key;
  return headers;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (API_URL_MISSING) {
    throw new ApiError("VITE_API_URL is not set for this deployment.", 0);
  }
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError("Can't reach the server. Is the API running?", 0);
  }
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    let code: string | undefined;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail)) detail = "Invalid request.";
      if (typeof body.code === "string") code = body.code;
    } catch {
      // non-JSON error body
    }
    throw new ApiError(detail, res.status, code);
  }
  return (await res.json()) as T;
}

function json(body: unknown): RequestInit {
  return {
    method: "POST",
    headers: buildHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  };
}

export const api = {
  getDataset: () =>
    request<{ dataset: DatasetSummary | null }>("/api/datasets/current", {
      headers: buildHeaders(),
    }),
  resetDataset: () =>
    request<{ deleted: boolean }>("/api/datasets/current", {
      method: "DELETE",
      headers: buildHeaders(),
    }),
  loadSample: () =>
    request<{ dataset: DatasetSummary }>("/api/datasets/sample", {
      method: "POST",
      headers: buildHeaders(),
    }),
  previewFile: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<DraftPreview>("/api/datasets/preview", {
      method: "POST",
      headers: buildHeaders(),
      body: form,
    });
  },
  previewText: (text: string) =>
    request<DraftPreview>("/api/datasets/preview-text", json({ text })),
  commit: (draftId: string, datasetName: string, tables: CommitTable[]) =>
    request<{ dataset: DatasetSummary }>(
      "/api/datasets/commit",
      json({ draft_id: draftId, dataset_name: datasetName, tables }),
    ),
  getGate: () =>
    request<GateInfo & { free_actions: number }>("/api/gate", { headers: buildHeaders() }),
  validateKey: (key: string) =>
    request<{ valid: boolean }>("/api/key/validate", {
      method: "POST",
      headers: { "X-Visitor-Id": getVisitorId(), "X-User-Api-Key": key },
    }),
  listConversations: () =>
    request<{ conversations: ConversationSummary[] }>("/api/conversations", {
      headers: buildHeaders(),
    }),
  getMessages: (conversationId: string) =>
    request<{ messages: StoredMessage[] }>(`/api/conversations/${conversationId}/messages`, {
      headers: buildHeaders(),
    }),
};
