import { useState } from "react";
import { api } from "../../lib/api";
import { setUserKey } from "../../lib/userKey";
import { Modal } from "../Modal";

export type KeyReason = "blocked" | "quota_exhausted" | "invalid_key" | "manual";

interface Props {
  open: boolean;
  reason: KeyReason;
  onClose: () => void;
  onSaved: () => void;
}

const HEADLINES: Record<KeyReason, string> = {
  blocked: "You've used your free tries. Enter your own OpenAI API key to continue.",
  quota_exhausted:
    "The shared demo key is out of quota right now. Enter your own OpenAI API key to continue.",
  invalid_key: "That OpenAI API key was rejected. Check it and try again.",
  manual: "Use your own OpenAI API key instead of the free tries.",
};

export function KeyModal({ open, reason, onClose, onSaved }: Props) {
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    const trimmed = key.trim();
    if (!trimmed) return;
    setBusy(true);
    setError(null);
    try {
      const { valid } = await api.validateKey(trimmed);
      if (!valid) {
        setError("OpenAI rejected this key.");
        return;
      }
      setUserKey(trimmed);
      setKey("");
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not validate the key.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="Bring your own key">
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
        <p className="text-sm leading-relaxed">{HEADLINES[reason]}</p>
        <p className="text-xs leading-relaxed text-muted">
          Your key stays in this browser (localStorage) and is sent over HTTPS with each request.
          The server uses it for that request only and never stores or logs it. Uploading, browsing
          and the sample dataset keep working without a key.
        </p>
        <div>
          <label htmlFor="api-key" className="mb-1 block text-xs font-medium">
            OpenAI API key
          </label>
          <input
            id="api-key"
            type="password"
            autoComplete="off"
            spellCheck={false}
            placeholder="sk-..."
            value={key}
            onChange={(e) => setKey(e.target.value)}
            className="w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm outline-none focus:border-accent"
          />
        </div>
        {error && <p className="text-sm text-danger">{error}</p>}
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-3 py-2 text-sm text-muted hover:bg-panel"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={busy || !key.trim()}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-ink disabled:opacity-50"
          >
            {busy ? "Checking…" : "Validate & save"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
