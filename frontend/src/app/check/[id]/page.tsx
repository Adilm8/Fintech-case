"use client";

import { useParams } from "next/navigation";
import { PaymentCheckView } from "@/components/PaymentCheckView";

export default function CheckPaymentPage() {
  const params = useParams<{ id: string }>();
  const rawId = typeof params.id === "string" ? params.id : "";
  let paymentId = rawId;
  try {
    paymentId = decodeURIComponent(rawId);
  } catch {
    paymentId = rawId;
  }

  return <PaymentCheckView paymentId={paymentId} />;
}
