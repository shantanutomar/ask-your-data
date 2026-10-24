import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import type { GateInfo } from "../types/events";
import { useUserKey } from "./useUserKey";

export interface GateState extends GateInfo {
  freeActions: number | null;
}

/** Remaining-free-tries state. Refetched when the user key changes; updated from `done` events. */
export function useGate() {
  const userKey = useUserKey();
  const [gate, setGate] = useState<GateState | null>(null);

  // biome-ignore lint/correctness/useExhaustiveDependencies: refetch whenever the key changes
  const refresh = useCallback(async () => {
    try {
      const g = await api.getGate();
      setGate({ mode: g.mode, remaining: g.remaining, freeActions: g.free_actions });
    } catch {
      // badge simply stays hidden if the API is unreachable
    }
  }, [userKey]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const applyDone = useCallback((info: GateInfo) => {
    setGate((prev) => ({ ...info, freeActions: prev?.freeActions ?? null }));
  }, []);

  const markBlocked = useCallback(() => {
    setGate((prev) => ({ mode: "blocked", remaining: 0, freeActions: prev?.freeActions ?? null }));
  }, []);

  return { gate, refresh, applyDone, markBlocked };
}
