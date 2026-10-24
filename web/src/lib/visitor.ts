const STORAGE_KEY = "ayd.visitor_id";
let memoryId: string | null = null;

/** Anonymous visitor id: a UUID kept in localStorage (no cookies, no auth). */
export function getVisitorId(): string {
  try {
    const existing = localStorage.getItem(STORAGE_KEY);
    if (existing) return existing;
    const id = crypto.randomUUID();
    localStorage.setItem(STORAGE_KEY, id);
    return id;
  } catch {
    memoryId ??= crypto.randomUUID();
    return memoryId;
  }
}
