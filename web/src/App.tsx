import { useCallback, useEffect, useState } from "react";
import { ChatPanel } from "./components/chat/ChatPanel";
import { DatasetPanel } from "./components/dataset/DatasetPanel";
import { KeyModal, type KeyReason } from "./components/gate/KeyModal";
import { TriesBadge } from "./components/gate/TriesBadge";
import { Modal } from "./components/Modal";
import { ThemeToggle } from "./components/ThemeToggle";
import { UploadDialog } from "./components/upload/UploadDialog";
import { useChatStream } from "./hooks/useChatStream";
import { useDataset } from "./hooks/useDataset";
import { useGate } from "./hooks/useGate";
import { SIDEBAR_MAX, SIDEBAR_MIN, useResizableWidth } from "./hooks/useResizableWidth";
import { useTheme } from "./hooks/useTheme";
import { useUserKey } from "./hooks/useUserKey";
import { ApiError } from "./lib/api";
import { clearUserKey } from "./lib/userKey";
import type { DatasetSummary } from "./types/api";

export default function App() {
  const userKey = useUserKey();
  const { gate, refresh: refreshGate, applyDone, markBlocked } = useGate();
  const { dataset, setDataset, loading, error: datasetError, loadSample, reset } = useDataset();

  const [keyModal, setKeyModal] = useState<{ open: boolean; reason: KeyReason }>({
    open: false,
    reason: "manual",
  });
  const [uploadOpen, setUploadOpen] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const sidebar = useResizableWidth();
  const theme = useTheme();

  const showKeyModal = useCallback(
    (reason: KeyReason) => {
      if (reason === "blocked") markBlocked();
      setKeyModal({ open: true, reason });
    },
    [markBlocked],
  );

  const chat = useChatStream({
    onGate: applyDone,
    onNeedKey: (code) => showKeyModal(code as KeyReason),
  });

  const datasetId = dataset?.id;
  // biome-ignore lint/correctness/useExhaustiveDependencies: restore only when the dataset first loads
  useEffect(() => {
    if (datasetId) void chat.restoreLatest();
  }, [datasetId]);

  const onDatasetReady = (next: DatasetSummary) => {
    chat.reset();
    setDataset(next);
    setUploadOpen(false);
    setDrawerOpen(false);
    setNotice(null);
  };

  const onSample = async () => {
    setBusy(true);
    setNotice(null);
    try {
      onDatasetReady(await loadSample());
    } catch (e) {
      setNotice(e instanceof ApiError ? e.message : "Could not load the sample dataset.");
    } finally {
      setBusy(false);
    }
  };

  const onReset = async () => {
    setBusy(true);
    try {
      await reset();
      chat.reset();
      setResetOpen(false);
      setDrawerOpen(false);
    } catch (e) {
      setNotice(e instanceof ApiError ? e.message : "Could not reset the dataset.");
    } finally {
      setBusy(false);
    }
  };

  const panel = (
    <DatasetPanel
      dataset={dataset}
      busy={busy}
      onUpload={() => {
        setUploadOpen(true);
        setDrawerOpen(false);
      }}
      onSample={() => void onSample()}
      onReset={() => setResetOpen(true)}
    />
  );

  const badge = (
    <TriesBadge
      gate={gate}
      hasKey={userKey !== null}
      onAddKey={() => showKeyModal("manual")}
      onRemoveKey={clearUserKey}
    />
  );

  return (
    <div
      className={`flex h-full bg-bg text-ink ${sidebar.dragging ? "cursor-col-resize select-none" : ""}`}
    >
      <aside className="hidden shrink-0 bg-panel md:block" style={{ width: sidebar.width }}>
        {panel}
      </aside>
      {/* biome-ignore lint/a11y/useSemanticElements: a focusable separator is the ARIA pattern for a splitter */}
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize dataset panel"
        aria-valuemin={SIDEBAR_MIN}
        aria-valuemax={SIDEBAR_MAX}
        aria-valuenow={sidebar.width}
        tabIndex={0}
        {...sidebar.handleProps}
        className={`hidden w-1.5 shrink-0 cursor-col-resize touch-none select-none border-l border-line transition-colors hover:bg-accent/30 focus-visible:bg-accent/40 focus-visible:outline-none md:block ${sidebar.dragging ? "bg-accent/40" : ""}`}
      />

      {drawerOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <button
            type="button"
            aria-label="Close dataset panel"
            onClick={() => setDrawerOpen(false)}
            className="absolute inset-0 bg-black/40"
          />
          <aside className="absolute inset-y-0 left-0 w-[85%] max-w-xs border-r border-line bg-panel shadow-xl">
            {panel}
          </aside>
        </div>
      )}

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b border-line px-4 py-2.5">
          <button
            type="button"
            onClick={() => setDrawerOpen(true)}
            aria-label="Open dataset panel"
            className="rounded-md border border-line px-2 py-1 text-sm md:hidden"
          >
            ☰
          </button>
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-semibold">{chat.title ?? "Ask your data"}</div>
          </div>
          {chat.messages.length > 0 && (
            <button
              type="button"
              onClick={chat.reset}
              disabled={chat.streaming}
              className="rounded-md px-2 py-1 text-sm text-muted hover:bg-panel disabled:opacity-50"
            >
              New chat
            </button>
          )}
          <div className="hidden sm:block">{badge}</div>
          <ThemeToggle mode={theme.mode} onCycle={theme.cycle} />
        </header>

        {notice && (
          <p role="alert" className="border-b border-line px-4 py-2 text-sm text-danger">
            {notice}
          </p>
        )}

        {loading ? (
          <div className="flex flex-1 items-center justify-center text-sm text-muted">Loading…</div>
        ) : datasetError ? (
          <div className="flex flex-1 items-center justify-center px-6 text-center text-sm text-danger">
            {datasetError}
          </div>
        ) : !dataset ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
            <h1 className="text-3xl font-semibold">Ask your data</h1>
            <p className="max-w-md text-sm leading-relaxed text-muted">
              Upload a CSV, JSON or Excel file, paste some text, or try the sample store dataset.
              Then ask questions in plain English and get answers with tables and charts.
            </p>
            <div className="flex flex-wrap justify-center gap-2">
              <button
                type="button"
                onClick={() => setUploadOpen(true)}
                className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-ink"
              >
                Upload or paste data
              </button>
              <button
                type="button"
                onClick={() => void onSample()}
                disabled={busy}
                className="rounded-lg border border-line px-4 py-2 text-sm hover:bg-panel disabled:opacity-50"
              >
                {busy ? "Loading…" : "Try the sample dataset"}
              </button>
            </div>
            <div className="sm:hidden">{badge}</div>
          </div>
        ) : (
          <ChatPanel
            dataset={dataset}
            messages={chat.messages}
            streaming={chat.streaming}
            onSend={(t) => void chat.send(t)}
            onStop={chat.stop}
            footer={<div className="sm:hidden">{badge}</div>}
          />
        )}
      </main>

      <UploadDialog
        open={uploadOpen}
        freeTextHint={
          gate?.mode === "byok" || userKey
            ? "Uses your OpenAI key."
            : "Extracting from text uses 1 of your free tries."
        }
        onClose={() => setUploadOpen(false)}
        onCommitted={onDatasetReady}
        onNeedKey={(code) => showKeyModal(code)}
        onGateChanged={() => void refreshGate()}
      />

      <KeyModal
        open={keyModal.open}
        reason={keyModal.reason}
        onClose={() => setKeyModal((k) => ({ ...k, open: false }))}
        onSaved={() => setKeyModal((k) => ({ ...k, open: false }))}
      />

      <Modal open={resetOpen} onClose={() => setResetOpen(false)} title="Reset dataset?">
        <p className="text-sm leading-relaxed">
          This deletes your dataset, all conversations and cached answers. You can upload data or
          load the sample again afterwards.
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={() => setResetOpen(false)}
            className="rounded-lg px-3 py-2 text-sm text-muted hover:bg-panel"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => void onReset()}
            disabled={busy}
            className="rounded-lg bg-danger px-4 py-2 text-sm font-medium text-bg disabled:opacity-50"
          >
            Reset
          </button>
        </div>
      </Modal>
    </div>
  );
}
