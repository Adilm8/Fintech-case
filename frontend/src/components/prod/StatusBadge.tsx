"use client";

import { Badge } from "@/components/ui/badge";
import { useT } from "@/i18n";
import type { ApprovalStatus, PaymentStatus } from "@/lib/prod/types";
import { cn } from "cn";

const PAYMENT_STATUS_CLASSES: Record<PaymentStatus, string> = {
  checked: "border-sky-200 bg-sky-50 text-sky-900",
  pending_approval: "border-amber-300/80 bg-amber-50 text-amber-900",
  approved: "border-[#00AB75]/35 bg-[#E8F8F2] text-[#006B49]",
  rejected: "border-red-200 bg-red-50 text-red-800",
  postponed: "border-slate-300 bg-slate-100 text-slate-700",
  signed: "border-[#00AB75]/45 bg-[#00AB75]/15 text-[#064A34]",
  cancelled: "border-border bg-muted text-muted-foreground",
};

const APPROVAL_STATUS_CLASSES: Record<ApprovalStatus, string> = {
  pending: "border-amber-300/80 bg-amber-50 text-amber-900",
  approved: "border-[#00AB75]/35 bg-[#E8F8F2] text-[#006B49]",
  rejected: "border-red-200 bg-red-50 text-red-800",
  superseded: "border-slate-300 bg-slate-100 text-slate-600",
};

export function StatusBadge({
  status,
  className,
}: {
  status: PaymentStatus;
  className?: string;
}) {
  const { t } = useT();
  return (
    <Badge
      variant="outline"
      className={cn(
        "h-auto min-h-6 px-2 py-0.5 text-xs font-medium",
        PAYMENT_STATUS_CLASSES[status] ?? PAYMENT_STATUS_CLASSES.checked,
        className
      )}
    >
      {t.prod.statuses[status] ?? status}
    </Badge>
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
  return (
    <Badge
      variant="outline"
      className={cn(
        "h-auto min-h-6 px-2 py-0.5 text-xs font-medium",
        APPROVAL_STATUS_CLASSES[status] ?? APPROVAL_STATUS_CLASSES.pending,
        className
      )}
    >
      {t.prod.approvalStatuses[status] ?? status}
    </Badge>
  );
}
