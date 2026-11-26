import type { Verdict } from "./types";

export type VerdictFilter = "all" | Verdict;

export type QueueSort =
  | "default"
  | "risk_desc"
  | "amount_desc"
  | "amount_asc"
  | "name_asc";

export interface QueuePreferences {
  verdictFilter: VerdictFilter;
  searchQuery: string;
  sort: QueueSort;
}

const QUEUE_PREFS_STORAGE_KEY = "business-shield.queue-prefs";

const VALID_VERDICT_FILTERS = new Set<string>([
  "all",
  "green",
  "yellow",
  "red",
  "grey",
  "invalid",
]);

const VALID_SORTS = new Set<string>([
  "default",
  "risk_desc",
  "amount_desc",
  "amount_asc",
  "name_asc",
]);

export const DEFAULT_QUEUE_PREFERENCES: QueuePreferences = {
  verdictFilter: "all",
  searchQuery: "",
  sort: "default",
};

let cachedPrefs: QueuePreferences | null = null;
const listeners = new Set<() => void>();

function readPreferencesFromStorage(): QueuePreferences {
  if (typeof window === "undefined") {
    return DEFAULT_QUEUE_PREFERENCES;
  }
  try {
    const raw = window.localStorage.getItem(QUEUE_PREFS_STORAGE_KEY);
    if (!raw) return DEFAULT_QUEUE_PREFERENCES;
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return DEFAULT_QUEUE_PREFERENCES;
    }
    const obj = parsed as Record<string, unknown>;
    const verdictFilter =
      typeof obj.verdictFilter === "string" &&
      VALID_VERDICT_FILTERS.has(obj.verdictFilter)
        ? (obj.verdictFilter as VerdictFilter)
        : "all";
    const searchQuery =
      typeof obj.searchQuery === "string" ? obj.searchQuery.slice(0, 120) : "";
    const sort =
      typeof obj.sort === "string" && VALID_SORTS.has(obj.sort)
        ? (obj.sort as QueueSort)
        : "default";

    return { verdictFilter, searchQuery, sort };
  } catch {
    return DEFAULT_QUEUE_PREFERENCES;
  }
}

function writePreferencesToStorage(next: QueuePreferences): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(QUEUE_PREFS_STORAGE_KEY, JSON.stringify(next));
  } catch {
    // Ignore storage write errors in restricted browsing contexts.
  }
}

export function getQueuePreferencesSnapshot(): QueuePreferences {
  if (typeof window === "undefined") {
    return DEFAULT_QUEUE_PREFERENCES;
  }
  if (cachedPrefs === null) {
    cachedPrefs = readPreferencesFromStorage();
  }
  return cachedPrefs;
}

export function getServerQueuePreferencesSnapshot(): QueuePreferences {
  return DEFAULT_QUEUE_PREFERENCES;
}

export function subscribeQueuePreferences(listener: () => void): () => void {
  listeners.add(listener);
  if (typeof window === "undefined") {
    return () => {
      listeners.delete(listener);
    };
  }
  const onStorage = (event: StorageEvent) => {
    if (event.key !== QUEUE_PREFS_STORAGE_KEY) return;
    cachedPrefs = readPreferencesFromStorage();
    listeners.forEach((cb) => cb());
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

export function updateQueuePreferences(
  updater:
    | Partial<QueuePreferences>
    | ((prev: QueuePreferences) => QueuePreferences)
): QueuePreferences {
  const prev = getQueuePreferencesSnapshot();
  const next =
    typeof updater === "function" ? updater(prev) : { ...prev, ...updater };
  cachedPrefs = next;
  writePreferencesToStorage(next);
  listeners.forEach((cb) => cb());
  return next;
}
