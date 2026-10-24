import type { ThemeMode } from "../hooks/useTheme";

const LABEL: Record<ThemeMode, string> = { system: "System", light: "Light", dark: "Dark" };

function Icon({ mode }: { mode: ThemeMode }) {
  const common = {
    width: 16,
    height: 16,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };
  if (mode === "light") {
    return (
      <svg {...common}>
        <title>Light theme</title>
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
      </svg>
    );
  }
  if (mode === "dark") {
    return (
      <svg {...common}>
        <title>Dark theme</title>
        <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <title>System theme</title>
      <rect x="3" y="4" width="18" height="12" rx="2" />
      <path d="M8 20h8M12 16v4" />
    </svg>
  );
}

export function ThemeToggle({ mode, onCycle }: { mode: ThemeMode; onCycle: () => void }) {
  return (
    <button
      type="button"
      onClick={onCycle}
      title={`Theme: ${LABEL[mode]} (click to change)`}
      aria-label={`Theme: ${LABEL[mode]}. Click to change.`}
      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted hover:bg-panel hover:text-ink"
    >
      <Icon mode={mode} />
    </button>
  );
}
