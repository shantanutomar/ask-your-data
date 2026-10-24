import { type KeyboardEvent, type ReactNode, useEffect, useRef, useState } from "react";

interface Props {
  streaming: boolean;
  disabled: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
  footer: ReactNode;
}

export function Composer({ streaming, disabled, onSend, onStop, footer }: Props) {
  const [text, setText] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  // biome-ignore lint/correctness/useExhaustiveDependencies: resize whenever the text changes
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [text]);

  const submit = () => {
    const value = text.trim();
    if (!value || streaming || disabled) return;
    onSend(value);
    setText("");
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="mx-auto w-full max-w-3xl px-4 pb-4">
      <div className="rounded-2xl border border-line bg-card p-2 shadow-sm focus-within:border-accent">
        <textarea
          ref={ref}
          rows={1}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          disabled={disabled}
          maxLength={2000}
          aria-label="Ask a question about your data"
          placeholder={
            disabled
              ? "Load a dataset to start asking questions"
              : "Ask a question about your data…"
          }
          className="block max-h-[200px] w-full resize-none bg-transparent px-2 py-1.5 text-[15px] outline-none placeholder:text-muted"
        />
        <div className="flex items-center justify-between gap-2 px-1 pt-1">
          <div className="min-w-0">{footer}</div>
          {streaming ? (
            <button
              type="button"
              onClick={onStop}
              aria-label="Stop generating"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-ink text-bg"
            >
              <span className="block h-3 w-3 rounded-[2px] bg-current" />
            </button>
          ) : (
            <button
              type="button"
              onClick={submit}
              disabled={disabled || !text.trim()}
              aria-label="Send"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-ink disabled:opacity-40"
            >
              ↑
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
