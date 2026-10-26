const PREFIX = "printechs_pwa_cache_v5:";

export type CacheEnvelope<T> = {
  savedAt: number;
  data: T;
};

export function cacheKey(...parts: string[]): string {
  return parts.filter(Boolean).join(":");
}

export function cacheRead<T>(key: string): CacheEnvelope<T> | null {
  try {
    const raw = localStorage.getItem(PREFIX + key);
    if (!raw) return null;
    return JSON.parse(raw) as CacheEnvelope<T>;
  } catch {
    return null;
  }
}

export function cacheWrite<T>(key: string, data: T): void {
  try {
    const envelope: CacheEnvelope<T> = { savedAt: Date.now(), data };
    localStorage.setItem(PREFIX + key, JSON.stringify(envelope));
  } catch {
    // Quota exceeded — ignore; network load still works.
  }
}

/** Returns data if saved within maxAgeMs. */
export function cacheGetFresh<T>(key: string, maxAgeMs: number): T | null {
  const entry = cacheRead<T>(key);
  if (!entry) return null;
  if (Date.now() - entry.savedAt > maxAgeMs) return null;
  return entry.data;
}

/** Stale-while-revalidate: return last saved payload up to maxStaleMs old. */
export function cacheGetStale<T>(
  key: string,
  maxStaleMs: number,
): { data: T; savedAt: number } | null {
  const entry = cacheRead<T>(key);
  if (!entry) return null;
  if (Date.now() - entry.savedAt > maxStaleMs) return null;
  return { data: entry.data, savedAt: entry.savedAt };
}

export function clearUserCache(email: string): void {
  const suffix = `:${email.toLowerCase()}`;
  const keys: string[] = [];
  for (let i = 0; i < localStorage.length; i++) {
    const k = localStorage.key(i);
    if (k?.startsWith(PREFIX) && k.includes(suffix)) keys.push(k);
  }
  keys.forEach((k) => localStorage.removeItem(k));
}

export function formatCacheAge(savedAt: number): string {
  const mins = Math.round((Date.now() - savedAt) / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 48) return `${hrs} hr ago`;
  return `${Math.round(hrs / 24)} days ago`;
}
