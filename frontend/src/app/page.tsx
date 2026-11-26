"use client";

import { Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAppData } from "@/components/AppShell";
import { PaymentCheckView } from "@/components/PaymentCheckView";
import { PaymentQueueScreen } from "@/components/PaymentQueueScreen";
import { getPaymentCheckHref } from "@/lib/queue-storage";

function HomeContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const {
    queue,
    approvals,
    approvalsError,
    isLoading,
    apiError,
    resetCounter,
    loadData,
    addCustomQueueItem,
    reportNetworkError,
  } = useAppData();

  const adHocId = searchParams.get("id")?.trim() || null;
  const openNewInitially = searchParams.get("new") === "1";

  useEffect(() => {
    if (openNewInitially && !adHocId) {
      window.dispatchEvent(new Event("business-shield:open-new-payment"));
      router.replace("/");
    }
  }, [openNewInitially, adHocId, router]);

  if (adHocId) {
    return <PaymentCheckView paymentId={adHocId} />;
  }

  return (
    <PaymentQueueScreen
      key={`queue-${resetCounter}`}
      queue={queue}
      approvals={approvals}
      approvalsError={approvalsError}
      isLoading={isLoading}
      hasError={Boolean(apiError)}
      openNewInitially={openNewInitially}
      onSelectPayment={(item) => {
        router.push(getPaymentCheckHref(item.id));
      }}
      onSelectPaymentById={(id) => {
        router.push(getPaymentCheckHref(id));
      }}
      onAddQueueItem={addCustomQueueItem}
      onRefreshQueue={() => loadData(false)}
      onNetworkError={reportNetworkError}
    />
  );
}

export default function Home() {
  const { homeResetNonce } = useAppData();
  return (
    <Suspense fallback={null}>
      <HomeContent key={homeResetNonce} />
    </Suspense>
  );
}
