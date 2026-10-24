import { useCallback, useEffect, useState } from "react";

export type ThemeMode = "system" | "light" | "dark";
const STORAGE_KEY = "ayd.theme";
const ORDER: ThemeMode[] = ["system", "light", "dark"];

function readStored(): ThemeMode {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

/** Theme preference: system (default) | light | dark. Applied as `data-theme` on <html>. */
export function useTheme() {
  const [mode, setMode] = useState<ThemeMode>(readStored);

  useEffect(() => {
    const root = document.documentElement;
    if (mode === "system") delete root.dataset.theme;
    else root.dataset.theme = mode;
    try {
      if (mode === "system") localStorage.removeItem(STORAGE_KEY);
      else localStorage.setItem(STORAGE_KEY, mode);
    } catch {
      // preference just won't persist
    }
  }, [mode]);

  const cycle = useCallback(() => {
    setMode((m) => ORDER[(ORDER.indexOf(m) + 1) % ORDER.length] as ThemeMode);
  }, []);

  return { mode, cycle };
}
