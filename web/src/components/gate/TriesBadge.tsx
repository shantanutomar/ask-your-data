import type { GateState } from "../../hooks/useGate";

interface Props {
  gate: GateState | null;
  hasKey: boolean;
  onAddKey: () => void;
  onRemoveKey: () => void;
}

export function TriesBadge({ gate, hasKey, onAddKey, onRemoveKey }: Props) {
  if (hasKey) {
    return (
      <div className="flex items-center gap-2 text-xs text-muted">
        <span className="rounded-full border border-line px-2 py-0.5">Using your OpenAI key</span>
        <button type="button" onClick={onRemoveKey} className="underline hover:text-ink">
          Remove key
        </button>
      </div>
    );
  }
  if (!gate) return null;
  if (gate.mode === "blocked" || gate.remaining === 0) {
    return (
      <button
        type="button"
        onClick={onAddKey}
        className="rounded-full border border-accent px-3 py-0.5 text-xs font-medium text-accent hover:bg-accent hover:text-accent-ink"
      >
        No free tries left · Add your key
      </button>
    );
  }
  return (
    <div className="flex items-center gap-2 text-xs text-muted">
      <span className="rounded-full border border-line px-2 py-0.5">
        {gate.remaining} free {gate.remaining === 1 ? "try" : "tries"} left
      </span>
      <button type="button" onClick={onAddKey} className="underline hover:text-ink">
        Use my key
      </button>
    </div>
  );
}
