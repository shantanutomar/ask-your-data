import type { Step } from "../../types/events";

const STEPS: { id: Step; label: string }[] = [
  { id: "reading_schema", label: "Reading schema" },
  { id: "writing_sql", label: "Writing SQL" },
  { id: "running_query", label: "Running query" },
  { id: "analysing", label: "Analysing" },
];

export function StatusLine({ step }: { step: Step | undefined }) {
  const current = STEPS.findIndex((s) => s.id === step);
  return (
    <output className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted">
      <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-accent" />
      {step === undefined ? (
        <span>Thinking…</span>
      ) : (
        STEPS.map((s, i) => (
          <span
            key={s.id}
            className={i === current ? "font-medium text-ink" : i < current ? "" : "opacity-40"}
          >
            {s.label}
            {i < STEPS.length - 1 && <span className="ml-2 opacity-50">→</span>}
          </span>
        ))
      )}
    </output>
  );
}
