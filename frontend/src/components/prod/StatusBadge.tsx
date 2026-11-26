"use client";

import { useT } from "@/i18n";
import type { ApprovalStatus, PaymentStatus } from "@/lib/prod/types";
import { cn } from "cn";

const PAYMENT_STATUS_DOT: Record<PaymentStatus, string> = {
  checked: "ui-dot-neutral",
  pending_approval: "ui-dot-warn",
  approved: "ui-dot-ok",
  rejected: "ui-dot-danger",
  postponed: "ui-dot-neutral",
  signed: "ui-dot-ok",
  cancelled: "ui-dot-neutral",
};

const APPROVAL_STATUS_DOT: Record<ApprovalStatus, string> = {
  pending: "ui-dot-warn",
  approved: "ui-dot-ok",
  rejected: "ui-dot-danger",
  superseded: "ui-dot-neutral",
};

export function StatusBadge({
  status,
  className,
}: {
  status: PaymentStatus;
  className?: string;
}) {
  const { t } = useT();
  const dotClass = PAYMENT_STATUS_DOT[status] ?? "ui-dot-neutral";
  const textToneClass =
    status === "rejected" ? "text-[var(--status-danger-text)]" : undefined;

  return (
    <span className={cn("ui-status", textToneClass, className)}>
      <span aria-hidden="true" className={cn("ui-status-dot", dotClass)} />
      <span>{t.prod.statuses[status] ?? status}</span>
    </span>
  );
}

export function ApprovalStatusBadge({
  status,
  className,
}: {
  status: ApprovalStatus;
  className?: string;
}) {
  const { t } = useT();
  const dotClass = APPROVAL_STATUS_DOT[status] ?? "ui-dot-neutral";
  const textToneClass =
    status === "rejected" ? "text-[var(--status-danger-text)]" : undefined;

  return (
    <span className={cn("ui-status", textToneClass, className)}>
      <span aria-hidden="true" className={cn("ui-status-dot", dotClass)} />
      <span>{t.prod.approvalStatuses[status] ?? status}</span>
    </span>
  );
}
