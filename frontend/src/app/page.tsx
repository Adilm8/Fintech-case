"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { AppHeader } from "@/components/AppHeader";
import { CheckScreen } from "@/components/CheckScreen";
import { DirectorScreen } from "@/components/DirectorScreen";
import { PaymentQueueScreen } from "@/components/PaymentQueueScreen";
import { Alert, AlertAction, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  getApprovals,
  getErrorMessage,
  getQueue,
  isNetworkUnreachableError,
  resetDemo,
} from "@/lib/api";
import type {
  Approval,
  CheckRequest,
  CheckResult,
  QueueItem,
  UserRole,
} from "@/lib/types";

interface SelectedPayment {
  request: CheckRequest;
  result: CheckResult;
}

export default function Home() {
  const [role, setRole] = useState<UserRole>("accountant");
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [selectedPayment, setSelectedPayment] =
    useState<SelectedPayment | null>(null);
  const [prefillRequest, setPrefillRequest] = useState<CheckRequest | null>(
    null
  );
  const [isLoadingQueue, setIsLoadingQueue] = useState(true);
  const [isResetting, setIsResetting] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);
  const [resetCounter, setResetCounter] = useState(0);

  const loadData = useCallback(async (showLoading = false) => {
    if (showLoading) setIsLoadingQueue(true);
    try {
      const [queueData, approvalsData] = await Promise.all([
        getQueue(),
        getApprovals(),
      ]);
      setQueue(queueData);
      setApprovals(approvalsData);
      setApiError(null);
    } catch (err) {
      setApiError(getErrorMessage(err));
    } finally {
      if (showLoading) setIsLoadingQueue(false);
    }
  }, []);

  const refreshApprovalsOnly = useCallback(async () => {
    try {
      const approvalsData = await getApprovals();
      setApprovals(approvalsData);
      setApiError((prev) => (prev && prev.includes("недоступен") ? null : prev));
    } catch (err) {
      if (isNetworkUnreachableError(err)) {
        setApiError(getErrorMessage(err));
      }
    }
  }, []);

  useEffect(() => {
    let active = true;
    Promise.all([getQueue(), getApprovals()])
      .then(([queueData, approvalsData]) => {
        if (!active) return;
        setQueue(queueData);
        setApprovals(approvalsData);
        setApiError(null);
      })
      .catch((err) => {
        if (!active) return;
        setApiError(getErrorMessage(err));
      })
      .finally(() => {
        if (active) setIsLoadingQueue(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const timer = setInterval(() => {
      refreshApprovalsOnly();
    }, 10000);
    return () => clearInterval(timer);
  }, [refreshApprovalsOnly]);

  const handleRoleChange = (nextRole: UserRole) => {
    setRole(nextRole);
    setSelectedPayment(null);
    loadData(false);
  };

  const handleResetDemo = async () => {
    setIsResetting(true);
    try {
      await resetDemo();
      setRole("accountant");
      setSelectedPayment(null);
      setPrefillRequest(null);
      setApiError(null);
      setResetCounter((count) => count + 1);
      await loadData(true);
    } catch (err) {
      setApiError(getErrorMessage(err));
    } finally {
      setIsResetting(false);
    }
  };

  const pendingApprovalsCount = approvals.filter(
    (item) => item.status === "pending"
  ).length;

  return (
    <div className="min-h-screen flex flex-col bg-background overflow-x-clip">
      <AppHeader
        role={role}
        onRoleChange={handleRoleChange}
        pendingCount={pendingApprovalsCount}
        onResetDemo={handleResetDemo}
        isResetting={isResetting}
        onLogoClick={() => setSelectedPayment(null)}
      />

      <main className="mx-auto w-full max-w-[1248px] flex-1 px-4 py-4 space-y-5 sm:px-6 sm:py-6 sm:space-y-6">
        {apiError && (
          <Alert
            variant="destructive"
            className="bg-red-50/90 border-red-300 px-3.5 py-3 pr-3.5 sm:pr-32"
          >
            <AlertTriangle className="size-4" />
            <AlertTitle>Ошибка соединения с сервером</AlertTitle>
            <AlertDescription className="break-words">{apiError}</AlertDescription>
            <AlertAction className="static col-span-full mt-2.5 sm:absolute sm:top-2.5 sm:right-2.5 sm:mt-0">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => loadData(true)}
                className="min-h-11 w-full gap-1.5 border-red-300 bg-white text-red-900 hover:bg-red-50 sm:min-h-8 sm:w-auto"
              >
                <RefreshCw className="size-3.5" />
                <span>Повторить</span>
              </Button>
            </AlertAction>
          </Alert>
        )}

        {role === "director" ? (
          <DirectorScreen
            key={`director-${resetCounter}`}
            approvals={approvals}
            isLoading={isLoadingQueue}
            onRefresh={() => loadData(false)}
            onNetworkError={(message) => setApiError(message)}
          />
        ) : selectedPayment ? (
          <CheckScreen
            key={`check-${resetCounter}-${selectedPayment.request.recipient_bin}-${selectedPayment.request.recipient_iik}-${selectedPayment.request.amount_kzt}`}
            request={selectedPayment.request}
            result={selectedPayment.result}
            approvals={approvals}
            onBack={() => {
              setSelectedPayment(null);
              void loadData(false);
            }}
            onFixRequisites={(req) => {
              setPrefillRequest(req);
              setSelectedPayment(null);
            }}
            onResultUpdate={(updatedResult) => {
              setSelectedPayment((prev) =>
                prev ? { ...prev, result: updatedResult } : prev
              );
              void loadData(false);
            }}
            onApprovalCreated={(createdApproval) => {
              setApprovals((prev) => {
                const exists = prev.some(
                  (item) => item.id === createdApproval.id
                );
                return exists
                  ? prev.map((item) =>
                      item.id === createdApproval.id ? createdApproval : item
                    )
                  : [...prev, createdApproval];
              });
              void refreshApprovalsOnly();
            }}
            onNetworkError={(message) => setApiError(message)}
          />
        ) : (
          <PaymentQueueScreen
            key={`queue-${resetCounter}-${
              prefillRequest ? JSON.stringify(prefillRequest) : "empty"
            }`}
            queue={queue}
            approvals={approvals}
            isLoading={isLoadingQueue}
            hasError={Boolean(apiError)}
            prefillRequest={prefillRequest}
            onSelectPayment={(request, result) => {
              setPrefillRequest(null);
              setSelectedPayment({ request, result });
            }}
            onNetworkError={(message) => setApiError(message)}
          />
        )}
      </main>
    </div>
  );
}
