"use client";

import { useMemo } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Inbox } from "lucide-react";
import { useAppData } from "@/components/AppShell";
import { CheckScreen } from "@/components/CheckScreen";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
      <div className="space-y-5">
        <div className="flex items-center justify-between gap-3">
          <Skeleton className="h-9 w-36 rounded-lg" />
          <Skeleton className="h-9 w-32 rounded-lg" />
        </div>
        <Card className="min-w-0">
          <CardContent className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="space-y-2 flex-1">
              <Skeleton className="h-3.5 w-40" />
              <Skeleton className="h-6 w-60" />
              <Skeleton className="h-4 w-72" />
            </div>
            <div className="space-y-2 sm:text-right">
              <Skeleton className="h-8 w-36 sm:ml-auto" />
              <Skeleton className="h-3.5 w-48 sm:ml-auto" />
            </div>
          </CardContent>
        </Card>
        <Skeleton className="h-20 w-full rounded-xl" />
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
          <Skeleton className="h-72 w-full rounded-xl" />
          <Skeleton className="h-56 w-full rounded-xl" />
        </div>
      </div>
    );
  }

  if (!item) {
    return (
      <div className="space-y-5">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={handleBack}
          className="min-h-11 gap-1.5 text-muted-foreground hover:text-foreground sm:min-h-9"
        >
          <ArrowLeft className="size-4" />
          <span>{t.check.backToList}</span>
        </Button>

        <Card>
          <CardContent className="flex flex-col items-center justify-center gap-3 py-16 px-4 text-center">
            <div className="flex size-12 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
              <Inbox className="size-6" />
            </div>
            <div className="space-y-1">
              <div className="text-base font-semibold text-foreground">
                {t.check.notFoundTitle}
              </div>
              <p className="max-w-md text-sm text-muted-foreground">
                {t.check.notFoundDescription}
              </p>
            </div>
            <Button
              type="button"
              variant="outline"
              onClick={handleBack}
              className="mt-1 min-h-11 gap-2 rounded-xl sm:min-h-9"
            >
              <ArrowLeft className="size-4" />
              <span>{t.check.backToList}</span>
            </Button>
          </CardContent>
        </Card>
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
