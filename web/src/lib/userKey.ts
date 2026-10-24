const STORAGE_KEY = "ayd.user_api_key";
let memoryKey: string | null = null;
const listeners = new Set<() => void>();

export function getUserKey(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY) ?? memoryKey;
  } catch {
    return memoryKey;
  }
}

function notify() {
  for (const l of listeners) l();
}

export function setUserKey(key: string): void {
  memoryKey = key;
  try {
    localStorage.setItem(STORAGE_KEY, key);
  } catch {
    // keep it in memory for this tab only
  }
  notify();
}

export function clearUserKey(): void {
  memoryKey = null;
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
  notify();
}

export function subscribeUserKey(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
