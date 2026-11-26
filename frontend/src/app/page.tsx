"use client";

import { useState } from "react";
import { useAppData } from "@/components/AppShell";
import { CheckScreen } from "@/components/CheckScreen";
import { PaymentQueueScreen } from "@/components/PaymentQueueScreen";
import type { CheckRequest, CheckResult } from "@/lib/types";

interface SelectedPayment {
  request: CheckRequest;
  result: CheckResult;
}

function HomeContent() {
  const {
    queue,
    approvals,
    approvalsError,
    isLoading,
    apiError,
    resetCounter,
    loadData,
    refreshApprovalsOnly,
    upsertApproval,
    addCustomQueueItem,
    reportNetworkError,
  } = useAppData();

  const [selectedPayment, setSelectedPayment] =
    useState<SelectedPayment | null>(null);
  const [prefillRequest, setPrefillRequest] = useState<CheckRequest | null>(
    null
  );

  if (selectedPayment) {
    return (
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
          upsertApproval(createdApproval);
          void refreshApprovalsOnly();
        }}
        onNetworkError={reportNetworkError}
      />
    );
  }

  return (
    <PaymentQueueScreen
      key={`queue-${resetCounter}`}
      queue={queue}
      approvals={approvals}
      approvalsError={approvalsError}
      isLoading={isLoading}
      hasError={Boolean(apiError)}
      prefillRequest={prefillRequest}
      onClearPrefill={() => setPrefillRequest(null)}
      onSelectPayment={(request, result) => {
        setPrefillRequest(null);
        setSelectedPayment({ request, result });
      }}
      onAddQueueItem={addCustomQueueItem}
      onRefreshQueue={() => loadData(false)}
      onNetworkError={reportNetworkError}
    />
  );
}

export default function Home() {
  const { homeResetNonce } = useAppData();
  return <HomeContent key={homeResetNonce} />;
}
