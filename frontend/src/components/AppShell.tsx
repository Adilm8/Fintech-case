"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
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
  loadData: (showLoading?: boolean) => Promise<void>;
  refreshApprovalsOnly: () => Promise<void>;
  upsertApproval: (createdApproval: Approval) => void;
  addCustomQueueItem: (request: CheckRequest, result: CheckResult) => string;
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
  const { lang, t } = useT();

  const [serverQueue, setServerQueue] = useState<QueueItem[]>([]);
  const [customQueueItems, setCustomQueueItems] = useState<QueueItem[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [approvalsError, setApprovalsError] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isResetting, setIsResetting] = useState(false);
  const [apiErrorState, setApiErrorState] = useState<ApiErrorState | null>(
    null
  );
  const [resetCounter, setResetCounter] = useState(0);
  const [homeResetNonce, setHomeResetNonce] = useState(0);
  const hasLoadedOnceRef = useRef(false);
  const customItemsRef = useRef<QueueItem[]>([]);

  useEffect(() => {
    customItemsRef.current = customQueueItems;
  }, [customQueueItems]);

  const loadData = useCallback(
    async (showLoading = false) => {
      if (showLoading) setIsLoading(true);
      try {
        const [queueResult, approvalsResult] = await Promise.allSettled([
          getQueue(lang),
          getApprovals(lang),
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
    [lang]
  );

  const refreshApprovalsOnly = useCallback(async () => {
    try {
      const approvalsData = await getApprovals(lang);
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
  }, [lang]);

  useEffect(() => {
    let active = true;
    const isInitialLoad = !hasLoadedOnceRef.current;

    Promise.allSettled([getQueue(lang), getApprovals(lang)])
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

    // Re-check any client-added custom payments when language changes so backend texts update too.
    const existingCustom = customItemsRef.current;
    if (existingCustom.length > 0) {
      Promise.all(
        existingCustom.map(async (item) => {
          try {
            const refreshed = await checkPayment(item.request, lang);
            return { ...item, result: refreshed };
          } catch {
            return item;
          }
        })
      ).then((updatedCustom) => {
        if (!active) return;
        setCustomQueueItems(updatedCustom);
      });
    }

    return () => {
      active = false;
    };
  }, [lang]);

  useEffect(() => {
    const timer = setInterval(() => {
      void refreshApprovalsOnly();
    }, 10000);
    return () => clearInterval(timer);
  }, [refreshApprovalsOnly]);

  const handleResetDemo = useCallback(async () => {
    setIsResetting(true);
    try {
      await resetDemo(lang);
      setCustomQueueItems([]);
      setApiErrorState(null);
      setApprovalsError(false);
      setResetCounter((count) => count + 1);
      setHomeResetNonce((count) => count + 1);
      await loadData(true);
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
      const id = `custom-${result.check_id}`;
      const fp = queueItemFingerprint(request);
      setCustomQueueItems((prev) => [
        { id, request, result },
        ...prev.filter((item) => queueItemFingerprint(item.request) !== fp),
      ]);
      return id;
    },
    []
  );

  const reportNetworkError = useCallback((message: string) => {
    setApiErrorState({ message, isNetwork: true });
  }, []);

  const mergedQueue = useMemo(() => {
    if (customQueueItems.length === 0) return serverQueue;
    const serverFingerprints = new Set(
      serverQueue.map((item) => queueItemFingerprint(item.request))
    );
    const uniqueCustom = customQueueItems.filter(
      (item) => !serverFingerprints.has(queueItemFingerprint(item.request))
    );
    return [...uniqueCustom, ...serverQueue];
  }, [customQueueItems, serverQueue]);

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
      loadData,
      refreshApprovalsOnly,
      upsertApproval,
      addCustomQueueItem,
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
      loadData,
      refreshApprovalsOnly,
      upsertApproval,
      addCustomQueueItem,
      reportNetworkError,
    ]
  );

  return (
    <AppDataContext.Provider value={contextValue}>
      <div className="min-h-screen flex flex-col bg-background overflow-x-clip">
        <AppHeader
          pendingCount={pendingApprovalsCount}
          onResetDemo={() => void handleResetDemo()}
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
