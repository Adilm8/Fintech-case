"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { usePathname, useRouter } from "next/navigation";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { AppHeader } from "@/components/AppHeader";
import {
  Alert,
  AlertAction,
  AlertDescription,
  AlertTitle,
} from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useT } from "@/i18n";
import {
  checkPayment,
  getApprovals,
  getErrorMessage,
  getQueue,
  isNetworkUnreachableError,
  resetDemo,
} from "@/lib/api";
import {
  AD_HOC_ID_PREFIX,
  clearLocalQueueState,
  getLocalQueueSnapshot,
  getServerLocalQueueSnapshot,
  subscribeLocalQueue,
  updateLocalQueueState,
} from "@/lib/queue-storage";
import { notify } from "@/lib/toast";
import type { Approval, CheckRequest, CheckResult, QueueItem } from "@/lib/types";

interface ApiErrorState {
  message: string;
  isNetwork: boolean;
}

interface AppDataContextValue {
  queue: QueueItem[];
  approvals: Approval[];
  approvalsError: boolean;
  isLoading: boolean;
  isResetting: boolean;
  apiError: string | null;
  resetCounter: number;
  homeResetNonce: number;
  analystMode: boolean;
  setAnalystMode: (enabled: boolean) => void;
  loadData: (showLoading?: boolean) => Promise<void>;
  refreshApprovalsOnly: () => Promise<void>;
  upsertApproval: (createdApproval: Approval) => void;
  addCustomQueueItem: (request: CheckRequest, result: CheckResult) => string;
  replaceQueueItem: (
    id: string,
    request: CheckRequest,
    result: CheckResult
  ) => string;
  updateLocalQueueItemResult: (id: string, result: CheckResult) => void;
  reportNetworkError: (message: string) => void;
}

const AppDataContext = createContext<AppDataContextValue | null>(null);

function queueItemFingerprint(request: CheckRequest): string {
  const bin = request.recipient_bin.replace(/\s+/g, "");
  const iik = request.recipient_iik.replace(/\s+/g, "").toUpperCase();
  const purpose = request.purpose.trim().toLowerCase();
  return `${bin}|${iik}|${request.amount_kzt}|${purpose}`;
}

export function useAppData(): AppDataContextValue {
  const ctx = useContext(AppDataContext);
  if (!ctx) {
    throw new Error("useAppData must be used inside AppShell");
  }
  return ctx;
}

export function AppShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { lang, mounted, t } = useT();

  const [serverQueue, setServerQueue] = useState<QueueItem[]>([]);
  const storedLocalQueue = useSyncExternalStore(
    subscribeLocalQueue,
    getLocalQueueSnapshot,
    getServerLocalQueueSnapshot
  );
  const localQueue = mounted ? storedLocalQueue : getServerLocalQueueSnapshot();

  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [approvalsError, setApprovalsError] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isResetting, setIsResetting] = useState(false);
  const [apiErrorState, setApiErrorState] = useState<ApiErrorState | null>(
    null
  );
  const [resetCounter, setResetCounter] = useState(0);
  const [homeResetNonce, setHomeResetNonce] = useState(0);
  const [analystModeState, setAnalystModeState] = useState(false);
  const hasLoadedOnceRef = useRef(false);
  const lastRecheckedLocalLangRef = useRef<string | null>(null);

  const isDirectorRoute = pathname.startsWith("/approvals");
  const effectiveAnalystMode = isDirectorRoute && analystModeState;

  const setAnalystMode = useCallback((enabled: boolean) => {
    setAnalystModeState(enabled);
  }, []);

  const loadData = useCallback(
    async (showLoading = false, analystOverride?: boolean) => {
      if (showLoading) setIsLoading(true);
      const useAnalyst = analystOverride ?? effectiveAnalystMode;
      try {
        const [queueResult, approvalsResult] = await Promise.allSettled([
          getQueue(lang, { analyst: useAnalyst }),
          getApprovals(lang, { analyst: useAnalyst }),
        ]);

        if (queueResult.status === "fulfilled") {
          setServerQueue(queueResult.value);
          setApiErrorState(null);
          hasLoadedOnceRef.current = true;
        } else {
          setApiErrorState({
            message: getErrorMessage(queueResult.reason),
            isNetwork: isNetworkUnreachableError(queueResult.reason),
          });
        }

        if (approvalsResult.status === "fulfilled") {
          setApprovals(approvalsResult.value);
          setApprovalsError(false);
        } else {
          setApprovalsError(true);
          if (queueResult.status === "rejected") {
            setApiErrorState({
              message: getErrorMessage(queueResult.reason),
              isNetwork: isNetworkUnreachableError(queueResult.reason),
            });
          }
        }
      } finally {
        if (showLoading) setIsLoading(false);
      }
    },
    [effectiveAnalystMode, lang]
  );

  const refreshApprovalsOnly = useCallback(async () => {
    try {
      const approvalsData = await getApprovals(lang, {
        analyst: effectiveAnalystMode,
      });
      setApprovals(approvalsData);
      setApprovalsError(false);
      setApiErrorState((prev) => (prev?.isNetwork ? null : prev));
    } catch (err) {
      setApprovalsError(true);
      if (isNetworkUnreachableError(err)) {
        setApiErrorState({
          message: getErrorMessage(err),
          isNetwork: true,
        });
      }
    }
  }, [effectiveAnalystMode, lang]);

  useEffect(() => {
    if (!mounted) return;
    let active = true;
    const isInitialLoad = !hasLoadedOnceRef.current;

    Promise.allSettled([
      getQueue(lang, { analyst: effectiveAnalystMode }),
      getApprovals(lang, { analyst: effectiveAnalystMode }),
    ])
      .then(([queueResult, approvalsResult]) => {
        if (!active) return;

        if (queueResult.status === "fulfilled") {
          setServerQueue(queueResult.value);
          setApiErrorState(null);
          hasLoadedOnceRef.current = true;
        } else {
          setApiErrorState({
            message: getErrorMessage(queueResult.reason),
            isNetwork: isNetworkUnreachableError(queueResult.reason),
          });
        }

        if (approvalsResult.status === "fulfilled") {
          setApprovals(approvalsResult.value);
          setApprovalsError(false);
        } else {
          setApprovalsError(true);
        }
      })
      .finally(() => {
        if (active && isInitialLoad) {
          setIsLoading(false);
        }
      });

    // Re-check any client-added or in-place edited payments when language changes so backend texts update too.
    const snapshot = getLocalQueueSnapshot();
    const hasLocalItems =
      snapshot.customItems.length > 0 ||
      Object.keys(snapshot.overrides).length > 0;
    const shouldRefreshLocal =
      hasLocalItems && lastRecheckedLocalLangRef.current !== lang;

    if (shouldRefreshLocal) {
      lastRecheckedLocalLangRef.current = lang;
      const customPromise = Promise.all(
        snapshot.customItems.map(async (item) => {
          try {
            const refreshed = await checkPayment(item.request, lang);
            return { ...item, result: refreshed };
          } catch {
            return item;
          }
        })
      );
      const overrideEntries = Object.entries(snapshot.overrides);
      const overridesPromise = Promise.all(
        overrideEntries.map(async ([key, item]) => {
          try {
            const refreshed = await checkPayment(item.request, lang);
            return [key, { ...item, result: refreshed }] as const;
          } catch {
            return [key, item] as const;
          }
        })
      );

      Promise.all([customPromise, overridesPromise]).then(
        ([updatedCustom, updatedOverrideEntries]) => {
          if (!active) return;
          const updatedCustomById = new Map(
            updatedCustom.map((item) => [item.id, item])
          );
          const updatedOverridesById = new Map(updatedOverrideEntries);

          updateLocalQueueState((prev) => ({
            customItems: prev.customItems.map(
              (item) => updatedCustomById.get(item.id) ?? item
            ),
            overrides: Object.fromEntries(
              Object.entries(prev.overrides).map(([key, item]) => [
                key,
                updatedOverridesById.get(key) ?? item,
              ])
            ),
          }));
        }
      );
    }

    return () => {
      active = false;
    };
  }, [effectiveAnalystMode, lang, mounted]);

  useEffect(() => {
    if (!mounted) return;
    const timer = setInterval(() => {
      void refreshApprovalsOnly();
    }, 10000);
    return () => clearInterval(timer);
  }, [mounted, refreshApprovalsOnly]);

  const handleResetDemo = useCallback(async () => {
    setIsResetting(true);
    try {
      await resetDemo(lang);
      clearLocalQueueState();
      lastRecheckedLocalLangRef.current = lang;
      setAnalystModeState(false);
      setApiErrorState(null);
      setApprovalsError(false);
      setResetCounter((count) => count + 1);
      setHomeResetNonce((count) => count + 1);
      if (
        pathname.startsWith("/check") ||
        (pathname === "/" &&
          typeof window !== "undefined" &&
          new URLSearchParams(window.location.search).has("id"))
      ) {
        router.push("/");
      }
      await loadData(true, false);
      notify.success(t.toast.demoResetTitle, t.toast.demoResetDescription);
    } catch (err) {
      const message = getErrorMessage(err);
      setApiErrorState({
        message,
        isNetwork: isNetworkUnreachableError(err),
      });
      notify.error(t.common.serverErrorTitle, message);
    } finally {
      setIsResetting(false);
    }
  }, [
    lang,
    loadData,
    pathname,
    router,
    t.common.serverErrorTitle,
    t.toast.demoResetDescription,
    t.toast.demoResetTitle,
  ]);

  const upsertApproval = useCallback((createdApproval: Approval) => {
    setApprovals((prev) => {
      const exists = prev.some((item) => item.id === createdApproval.id);
      return exists
        ? prev.map((item) =>
            item.id === createdApproval.id ? createdApproval : item
          )
        : [...prev, createdApproval];
    });
    setApprovalsError(false);
  }, []);

  const addCustomQueueItem = useCallback(
    (request: CheckRequest, result: CheckResult): string => {
      const id = `${AD_HOC_ID_PREFIX}${result.check_id}`;
      const fp = queueItemFingerprint(request);
      updateLocalQueueState((prev) => ({
        ...prev,
        customItems: [
          { id, request, result },
          ...prev.customItems.filter(
            (item) => queueItemFingerprint(item.request) !== fp
          ),
        ],
      }));
      return id;
    },
    []
  );

  const replaceQueueItem = useCallback(
    (id: string, request: CheckRequest, result: CheckResult): string => {
      updateLocalQueueState((prev) => {
        const existsInCustom = prev.customItems.some((item) => item.id === id);
        if (existsInCustom) {
          return {
            ...prev,
            customItems: prev.customItems.map((item) =>
              item.id === id ? { id, request, result } : item
            ),
          };
        }
        return {
          ...prev,
          overrides: {
            ...prev.overrides,
            [id]: { id, request, result },
          },
        };
      });
      return id;
    },
    []
  );

  const updateLocalQueueItemResult = useCallback(
    (id: string, result: CheckResult) => {
      updateLocalQueueState((prev) => {
        if (prev.customItems.some((item) => item.id === id)) {
          return {
            ...prev,
            customItems: prev.customItems.map((item) =>
              item.id === id ? { ...item, result } : item
            ),
          };
        }
        if (id in prev.overrides) {
          return {
            ...prev,
            overrides: {
              ...prev.overrides,
              [id]: { ...prev.overrides[id], result },
            },
          };
        }
        return prev;
      });
    },
    []
  );

  const reportNetworkError = useCallback((message: string) => {
    setApiErrorState({ message, isNetwork: true });
  }, []);

  const mergedQueue = useMemo(() => {
    const resolvedServerQueue = serverQueue.map(
      (item) => localQueue.overrides[item.id] ?? item
    );
    if (localQueue.customItems.length === 0) {
      return resolvedServerQueue;
    }
    const serverIds = new Set(resolvedServerQueue.map((item) => item.id));
    const serverFingerprints = new Set(
      resolvedServerQueue.map((item) => queueItemFingerprint(item.request))
    );
    const uniqueCustom = localQueue.customItems.filter(
      (item) =>
        !serverIds.has(item.id) &&
        !serverFingerprints.has(queueItemFingerprint(item.request))
    );
    return [...uniqueCustom, ...resolvedServerQueue];
  }, [localQueue.customItems, localQueue.overrides, serverQueue]);

  const pendingApprovalsCount = useMemo(
    () => approvals.filter((item) => item.status === "pending").length,
    [approvals]
  );

  const contextValue = useMemo<AppDataContextValue>(
    () => ({
      queue: mergedQueue,
      approvals,
      approvalsError,
      isLoading,
      isResetting,
      apiError: apiErrorState?.message ?? null,
      resetCounter,
      homeResetNonce,
      analystMode: effectiveAnalystMode,
      setAnalystMode,
      loadData: (showLoading?: boolean) => loadData(showLoading),
      refreshApprovalsOnly,
      upsertApproval,
      addCustomQueueItem,
      replaceQueueItem,
      updateLocalQueueItemResult,
      reportNetworkError,
    }),
    [
      mergedQueue,
      approvals,
      approvalsError,
      isLoading,
      isResetting,
      apiErrorState,
      resetCounter,
      homeResetNonce,
      effectiveAnalystMode,
      setAnalystMode,
      loadData,
      refreshApprovalsOnly,
      upsertApproval,
      addCustomQueueItem,
      replaceQueueItem,
      updateLocalQueueItemResult,
      reportNetworkError,
    ]
  );

  return (
    <AppDataContext.Provider value={contextValue}>
      <div className="min-h-screen flex flex-col bg-background overflow-x-clip">
        <AppHeader
          pendingCount={pendingApprovalsCount}
          onResetDemo={handleResetDemo}
          isResetting={isResetting}
          onHomeReset={() => setHomeResetNonce((count) => count + 1)}
        />

        <main className="mx-auto w-full max-w-[1248px] flex-1 px-4 py-4 space-y-5 sm:px-6 sm:py-6 sm:space-y-6">
          {apiErrorState && (
            <Alert
              variant="destructive"
              className="rounded-2xl bg-red-50/90 border-red-300 px-3.5 py-3 pr-3.5 sm:pr-32"
            >
              <AlertTriangle className="size-4" />
              <AlertTitle>{t.common.serverErrorTitle}</AlertTitle>
              <AlertDescription className="break-words">
                {apiErrorState.message}
              </AlertDescription>
              <AlertAction className="static col-span-full mt-2.5 sm:absolute sm:top-2.5 sm:right-2.5 sm:mt-0">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => void loadData(true)}
                  className="min-h-11 w-full gap-1.5 border-red-300 bg-white text-red-900 hover:bg-red-50 sm:min-h-8 sm:w-auto"
                >
                  <RefreshCw className="size-3.5" />
                  <span>{t.common.retry}</span>
                </Button>
              </AlertAction>
            </Alert>
          )}

          {children}
        </main>
      </div>
    </AppDataContext.Provider>
  );
}
