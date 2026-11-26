import type { QueueItem } from "./types";

export const AD_HOC_ID_PREFIX = "custom-";

export function isAdHocPaymentId(id: string): boolean {
  return id.startsWith(AD_HOC_ID_PREFIX);
}

export function getPaymentCheckHref(id: string): string {
  const encoded = encodeURIComponent(id);
  return isAdHocPaymentId(id) ? `/?id=${encoded}` : `/check/${encoded}`;
}

const CUSTOM_QUEUE_STORAGE_KEY = "business-shield.custom-queue";
const QUEUE_OVERRIDES_STORAGE_KEY = "business-shield.queue-overrides";

export interface LocalQueueState {
  customItems: QueueItem[];
  overrides: Record<string, QueueItem>;
}

const EMPTY_LOCAL_QUEUE_STATE: LocalQueueState = {
  customItems: [],
  overrides: {},
};

let cachedState: LocalQueueState | null = null;
const listeners = new Set<() => void>();

function isValidQueueItem(value: unknown): value is QueueItem {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<QueueItem>;
  return (
    typeof candidate.id === "string" &&
    Boolean(candidate.request) &&
    typeof candidate.request === "object" &&
    Boolean(candidate.result) &&
    typeof candidate.result === "object"
  );
}

function readLocalQueueStateFromStorage(): LocalQueueState {
  if (typeof window === "undefined") {
    return EMPTY_LOCAL_QUEUE_STATE;
  }
  let customItems: QueueItem[] = [];
  let overrides: Record<string, QueueItem> = {};

  try {
    const rawCustom = window.localStorage.getItem(CUSTOM_QUEUE_STORAGE_KEY);
    if (rawCustom) {
      const parsed: unknown = JSON.parse(rawCustom);
      if (Array.isArray(parsed)) {
        customItems = parsed.filter(isValidQueueItem);
      }
    }
  } catch {
    customItems = [];
  }

  try {
    const rawOverrides = window.localStorage.getItem(
      QUEUE_OVERRIDES_STORAGE_KEY
    );
    if (rawOverrides) {
      const parsed: unknown = JSON.parse(rawOverrides);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        const nextOverrides: Record<string, QueueItem> = {};
        for (const [key, item] of Object.entries(
          parsed as Record<string, unknown>
        )) {
          if (isValidQueueItem(item)) {
            nextOverrides[key] = item;
          }
        }
        overrides = nextOverrides;
      }
    }
  } catch {
    overrides = {};
  }

  if (customItems.length === 0 && Object.keys(overrides).length === 0) {
    return EMPTY_LOCAL_QUEUE_STATE;
  }

  return { customItems, overrides };
}

function writeLocalQueueStateToStorage(next: LocalQueueState): void {
  if (typeof window === "undefined") return;
  try {
    if (next.customItems.length === 0) {
      window.localStorage.removeItem(CUSTOM_QUEUE_STORAGE_KEY);
    } else {
      window.localStorage.setItem(
        CUSTOM_QUEUE_STORAGE_KEY,
        JSON.stringify(next.customItems)
      );
    }
    if (Object.keys(next.overrides).length === 0) {
      window.localStorage.removeItem(QUEUE_OVERRIDES_STORAGE_KEY);
    } else {
      window.localStorage.setItem(
        QUEUE_OVERRIDES_STORAGE_KEY,
        JSON.stringify(next.overrides)
      );
    }
  } catch {
    // Ignore storage write errors in restricted browsing contexts.
  }
}

export function getLocalQueueSnapshot(): LocalQueueState {
  if (typeof window === "undefined") {
    return EMPTY_LOCAL_QUEUE_STATE;
  }
  if (cachedState === null) {
    cachedState = readLocalQueueStateFromStorage();
  }
  return cachedState;
}

export function getServerLocalQueueSnapshot(): LocalQueueState {
  return EMPTY_LOCAL_QUEUE_STATE;
}

export function subscribeLocalQueue(listener: () => void): () => void {
  listeners.add(listener);
  if (typeof window === "undefined") {
    return () => {
      listeners.delete(listener);
    };
  }
  const onStorage = (event: StorageEvent) => {
    if (
      event.key !== CUSTOM_QUEUE_STORAGE_KEY &&
      event.key !== QUEUE_OVERRIDES_STORAGE_KEY
    ) {
      return;
    }
    cachedState = readLocalQueueStateFromStorage();
    listeners.forEach((cb) => cb());
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

export function updateLocalQueueState(
  updater: (prev: LocalQueueState) => LocalQueueState
): LocalQueueState {
  const prev = getLocalQueueSnapshot();
  const next = updater(prev);
  cachedState = next;
  writeLocalQueueStateToStorage(next);
  listeners.forEach((cb) => cb());
  return next;
}

export function clearLocalQueueState(): void {
  cachedState = EMPTY_LOCAL_QUEUE_STATE;
  writeLocalQueueStateToStorage(EMPTY_LOCAL_QUEUE_STATE);
  listeners.forEach((cb) => cb());
}
