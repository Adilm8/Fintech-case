"use client";

import { useMemo } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { useAppData } from "@/components/AppShell";
import { CheckScreen } from "@/components/CheckScreen";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useT } from "@/i18n";

interface PaymentCheckViewProps {
  paymentId: string;
}

export function PaymentCheckView({ paymentId }: PaymentCheckViewProps) {
  const router = useRouter();
  const { mounted, t } = useT();
  const {
    queue,
    approvals,
    isLoading,
    resetCounter,
    loadData,
    refreshApprovalsOnly,
    upsertApproval,
    replaceQueueItem,
    updateLocalQueueItemResult,
    reportNetworkError,
  } = useAppData();

  const item = useMemo(
    () => queue.find((entry) => entry.id === paymentId) ?? null,
    [queue, paymentId]
  );

  const handleBack = () => {
    router.push("/");
    void loadData(false);
  };

  if (!mounted || (isLoading && !item)) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between gap-3">
          <Skeleton className="h-9 w-36 rounded-[6px]" />
          <Skeleton className="h-9 w-32 rounded-[6px]" />
        </div>
        <div className="ui-panel min-w-0 p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex-1 space-y-2">
              <Skeleton className="h-3.5 w-40 rounded-[6px]" />
              <Skeleton className="h-6 w-60 rounded-[6px]" />
              <Skeleton className="h-4 w-72 rounded-[6px]" />
            </div>
            <div className="space-y-2 sm:text-right">
              <Skeleton className="h-7 w-36 rounded-[6px] sm:ml-auto" />
              <Skeleton className="h-3.5 w-48 rounded-[6px] sm:ml-auto" />
            </div>
          </div>
        </div>
        <Skeleton className="h-16 w-full rounded-[6px]" />
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
          <Skeleton className="h-72 w-full rounded-[8px]" />
          <Skeleton className="h-56 w-full rounded-[8px]" />
        </div>
      </div>
    );
  }

  if (!item) {
    return (
      <div className="space-y-4">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={handleBack}
          className="min-h-10 gap-1.5 text-muted-foreground hover:text-foreground sm:min-h-8"
        >
          <ArrowLeft className="size-4" />
          <span>{t.check.backToList}</span>
        </Button>

        <div className="ui-panel">
          <div className="ui-empty">
            <div className="ui-empty-title">{t.check.notFoundTitle}</div>
            <p className="ui-empty-desc">{t.check.notFoundDescription}</p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleBack}
              className="mt-2 min-h-10 gap-1.5 sm:min-h-8"
            >
              <ArrowLeft className="size-4" />
              <span>{t.check.backToList}</span>
            </Button>
          </div>
        </div>
      </div>
    );
  }

  const requestKey = [
    item.request.recipient_bin,
    item.request.recipient_iik,
    item.request.recipient_bik,
    item.request.amount_kzt,
    item.request.recipient_name,
    item.request.purpose,
  ].join("|");

  return (
    <CheckScreen
      key={`check-${resetCounter}-${item.id}-${requestKey}`}
      paymentId={item.id}
      request={item.request}
      result={item.result}
      approvals={approvals}
      onBack={handleBack}
      onPaymentFixed={(updatedRequest, updatedResult) => {
        replaceQueueItem(item.id, updatedRequest, updatedResult);
      }}
      onResultUpdate={(updatedResult) => {
        updateLocalQueueItemResult(item.id, updatedResult);
        void loadData(false);
      }}
      onApprovalCreated={(createdApproval) => {
        upsertApproval(createdApproval);
        void refreshApprovalsOnly();
      }}
      onNetworkError={reportNetworkError}
    />
  );
}
