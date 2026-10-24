import { useSyncExternalStore } from "react";
import { getUserKey, subscribeUserKey } from "../lib/userKey";

export function useUserKey(): string | null {
  return useSyncExternalStore(subscribeUserKey, getUserKey, () => null);
}
