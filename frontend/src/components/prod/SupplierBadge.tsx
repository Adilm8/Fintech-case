"use client";

import { AlertTriangle, History, ShieldCheck, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { useT } from "@/i18n";
import { REQUISITES_CHANGED_BADGE_DAYS } from "@/lib/prod/types";
import { cn } from "cn";

interface SupplierBadgeProps {
  requisitesChangedDaysAgo: number | null;
  hasPendingChange?: boolean;
  isNewSupplier?: boolean;
  trustedAccountsCount?: number;
  className?: string;
}

export function SupplierBadge({
  requisitesChangedDaysAgo,
  hasPendingChange = false,
  isNewSupplier = false,
  trustedAccountsCount,
  className,
}: SupplierBadgeProps) {
  const { t, interpolate, plural } = useT();

  const showChangedBadge =
    requisitesChangedDaysAgo !== null &&
    requisitesChangedDaysAgo >= 0 &&
    requisitesChangedDaysAgo <= REQUISITES_CHANGED_BADGE_DAYS;

  const showTrustedCount =
    typeof trustedAccountsCount === "number" && trustedAccountsCount > 0;

  if (
    !showChangedBadge &&
    !hasPendingChange &&
    !isNewSupplier &&
    !showTrustedCount
  ) {
    return null;
  }

  const changedLabel =
    requisitesChangedDaysAgo === 0
      ? t.prod.supplier.changedToday
      : interpolate(t.prod.supplier.changedDaysAgo, {
          days: plural(requisitesChangedDaysAgo ?? 0, t.prod.plurals.days),
        });

  return (
    <div className={cn("flex flex-wrap items-center gap-1.5", className)}>
      {showChangedBadge && (
        <Badge
          variant="outline"
          className="h-auto gap-1 border-amber-300/90 bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-900"
        >
          <History className="size-3 shrink-0 text-amber-700" />
          <span>{changedLabel}</span>
        </Badge>
      )}

      {hasPendingChange && (
        <Badge
          variant="outline"
          className="h-auto gap-1 border-orange-300 bg-orange-50 px-2 py-0.5 text-[11px] font-medium text-orange-900"
        >
          <AlertTriangle className="size-3 shrink-0 text-orange-700" />
          <span>{t.prod.supplier.pendingChangeBadge}</span>
        </Badge>
      )}

      {isNewSupplier && !hasPendingChange && (
        <Badge
          variant="outline"
          className="h-auto gap-1 border-slate-300 bg-slate-100/80 px-2 py-0.5 text-[11px] font-medium text-slate-700"
        >
          <Sparkles className="size-3 shrink-0 text-slate-500" />
          <span>{t.prod.supplier.newSupplierBadge}</span>
        </Badge>
      )}

      {showTrustedCount && (
        <Badge
          variant="outline"
          className="h-auto gap-1 border-[#00AB75]/35 bg-[#E8F8F2] px-2 py-0.5 text-[11px] font-medium text-[#006B49]"
        >
          <ShieldCheck className="size-3 shrink-0" />
          <span>
            {interpolate(t.prod.supplier.trustedCountBadge, {
              count: trustedAccountsCount,
            })}
          </span>
        </Badge>
      )}
    </div>
  );
}
