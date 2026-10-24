import { type DragEvent, useState } from "react";
import { ApiError, api } from "../../lib/api";
import type { CommitTable, DatasetSummary, DraftPreview } from "../../types/api";
import { Modal } from "../Modal";
import { PreviewEditor } from "./PreviewEditor";

interface Props {
  open: boolean;
  freeTextHint: string;
  onClose: () => void;
  onCommitted: (dataset: DatasetSummary) => void;
  onNeedKey: (code: "blocked" | "quota_exhausted" | "invalid_key") => void;
  onGateChanged: () => void;
}

type Tab = "file" | "text";
const MAX_TEXT = 20000;

export function UploadDialog({
  open,
  freeTextHint,
  onClose,
  onCommitted,
  onNeedKey,
  onGateChanged,
}: Props) {
  const [tab, setTab] = useState<Tab>("file");
  const [preview, setPreview] = useState<DraftPreview | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  const close = () => {
    setPreview(null);
    setError(null);
    setText("");
    onClose();
  };

  const handleError = (e: unknown) => {
    if (
      e instanceof ApiError &&
      (e.code === "blocked" || e.code === "quota_exhausted" || e.code === "invalid_key")
    ) {
      onNeedKey(e.code);
      setError(null);
      return;
    }
    setError(e instanceof Error ? e.message : "Something went wrong.");
  };

  const previewFile = async (file: File | undefined) => {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      setPreview(await api.previewFile(file));
    } catch (e) {
      handleError(e);
    } finally {
      setBusy(false);
    }
  };

  const previewText = async () => {
    setBusy(true);
    setError(null);
    try {
      setPreview(await api.previewText(text));
      onGateChanged();
    } catch (e) {
      handleError(e);
    } finally {
      setBusy(false);
    }
  };

  const commit = async (name: string, tables: CommitTable[]) => {
    if (!preview) return;
    setBusy(true);
    setError(null);
    try {
      const { dataset } = await api.commit(preview.draft_id, name, tables);
      setPreview(null);
      setText("");
      onCommitted(dataset);
    } catch (e) {
      handleError(e);
    } finally {
      setBusy(false);
    }
  };

  const onDrop = (e: DragEvent<HTMLLabelElement>) => {
    e.preventDefault();
    setDragging(false);
    void previewFile(e.dataTransfer.files[0]);
  };

  return (
    <Modal open={open} onClose={close} title={preview ? "Review your data" : "Add your data"} wide>
      {preview ? (
        <PreviewEditor
          preview={preview}
          busy={busy}
          error={error}
          onBack={() => {
            setPreview(null);
            setError(null);
          }}
          onCommit={(n, t) => void commit(n, t)}
        />
      ) : (
        <div className="space-y-4">
          <div className="flex gap-1 rounded-lg bg-panel p-1 text-sm">
            {(["file", "text"] as const).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => {
                  setTab(t);
                  setError(null);
                }}
                className={`flex-1 rounded-md px-3 py-1.5 ${tab === t ? "bg-card font-medium shadow-sm" : "text-muted"}`}
              >
                {t === "file" ? "Upload a file" : "Paste text"}
              </button>
            ))}
          </div>

          {tab === "file" ? (
            <label
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              className={`flex cursor-pointer flex-col items-center justify-center gap-1 rounded-xl border-2 border-dashed px-4 py-12 text-center ${dragging ? "border-accent bg-panel" : "border-line"}`}
            >
              <span className="font-medium">
                {busy ? "Reading file…" : "Drop a file here, or click to browse"}
              </span>
              <span className="text-xs text-muted">
                CSV, JSON (array of records) or Excel · up to 5 MB, 50,000 rows
              </span>
              <input
                type="file"
                accept=".csv,.tsv,.json,.xlsx,.xlsm"
                className="sr-only"
                disabled={busy}
                onChange={(e) => {
                  void previewFile(e.target.files?.[0]);
                  e.target.value = "";
                }}
              />
            </label>
          ) : (
            <div className="space-y-2">
              <label htmlFor="paste-text" className="block text-xs font-medium">
                Paste a list, a table, or notes containing data
              </label>
              <textarea
                id="paste-text"
                rows={10}
                value={text}
                maxLength={MAX_TEXT}
                onChange={(e) => setText(e.target.value)}
                placeholder={"Alice, Berlin, 34\nBob, Paris, 28\n..."}
                className="w-full resize-y rounded-lg border border-line bg-bg px-3 py-2 font-mono text-sm outline-none focus:border-accent"
              />
              <div className="flex items-center justify-between gap-3">
                <span className="text-xs text-muted">{freeTextHint}</span>
                <button
                  type="button"
                  disabled={busy || !text.trim()}
                  onClick={() => void previewText()}
                  className="shrink-0 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-ink disabled:opacity-50"
                >
                  {busy ? "Extracting…" : "Extract tables"}
                </button>
              </div>
            </div>
          )}

          {error && (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
          )}
        </div>
      )}
    </Modal>
  );
}
