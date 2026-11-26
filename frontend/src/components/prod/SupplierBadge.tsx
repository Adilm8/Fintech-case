"use client";

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
    <div className={cn("flex flex-wrap items-center gap-x-3 gap-y-1", className)}>
      {showChangedBadge && (
        <span className="ui-status text-[var(--status-warn-text)]">
          <span aria-hidden="true" className="ui-status-dot ui-dot-warn" />
          <span>{changedLabel}</span>
        </span>
      )}

      {hasPendingChange && (
        <span className="ui-status text-[var(--status-warn-text)]">
          <span aria-hidden="true" className="ui-status-dot ui-dot-warn" />
          <span>{t.prod.supplier.pendingChangeBadge}</span>
        </span>
      )}

      {isNewSupplier && !hasPendingChange && (
        <span className="ui-status text-muted-foreground">
          <span aria-hidden="true" className="ui-status-dot ui-dot-neutral" />
          <span>{t.prod.supplier.newSupplierBadge}</span>
        </span>
      )}

      {showTrustedCount && (
        <span className="ui-status text-[var(--status-ok-text)]">
          <span aria-hidden="true" className="ui-status-dot ui-dot-ok" />
          <span>
            {interpolate(t.prod.supplier.trustedCountBadge, {
              count: trustedAccountsCount,
            })}
          </span>
        </span>
      )}
    </div>
  );
}
