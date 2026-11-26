"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AlertTriangle, ArrowLeft, RefreshCw } from "lucide-react";
import { ApprovalsList } from "@/components/prod/ApprovalsList";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useT } from "@/i18n";
import { getApprovals, getProdErrorMessage } from "@/lib/prod/api";
import { useSession } from "@/lib/prod/session";
import type { Approval, ApprovalStatus } from "@/lib/prod/types";
import { cn } from "cn";

type StatusFilter = "all" | ApprovalStatus;

export default function ProdDirectorPage() {
  const { t, lang } = useT();
  const { session } = useSession();

  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [refreshNonce, setRefreshNonce] = useState(0);
  const fetchKey = `${lang}|${statusFilter}|${refreshNonce}`;
  const [loadState, setLoadState] = useState<{
    key: string;
    approvals: Approval[];
    error: string | null;
  } | null>(null);

  const role = session?.user.role ?? "analyst";

  useEffect(() => {
    const controller = new AbortController();

    getApprovals(
      statusFilter === "all" ? undefined : { status: statusFilter },
      lang,
      { signal: controller.signal }
    )
      .then((list) => {
        setLoadState({ key: fetchKey, approvals: list, error: null });
      })
      .catch((err) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setLoadState((prev) => ({
          key: fetchKey,
          approvals: prev?.approvals ?? [],
          error: getProdErrorMessage(err),
        }));
      });

    return () => controller.abort();
  }, [fetchKey, lang, statusFilter]);

  const approvals = useMemo(
    () => loadState?.approvals ?? [],
    [loadState]
  );
  const error = loadState?.error ?? null;
  const isLoading = loadState === null || loadState.key !== fetchKey;

  const handleRefresh = useCallback(() => {
    setRefreshNonce((n) => n + 1);
  }, []);

  const stats = useMemo(() => {
    const pending = approvals.filter((a) => a.status === "pending");
    const resolved = approvals.filter((a) => a.status !== "pending");
    const highRisk = pending.filter(
      (a) => a.check.verdict === "red" || a.check.verdict === "invalid"
    ).length;
    const trusted = resolved.filter(
      (a) => a.status === "approved" && a.trust_account
    ).length;
    return {
      pendingCount: pending.length,
      highRiskCount: highRisk,
      resolvedCount: resolved.length,
      trustedCount: trusted,
    };
  }, [approvals]);

  const filterOptions: Array<{ value: StatusFilter; label: string }> = [
    { value: "all", label: t.prod.approvals.filterAll },
    { value: "pending", label: t.prod.approvals.filterPending },
    { value: "approved", label: t.prod.approvals.filterApproved },
    { value: "rejected", label: t.prod.approvals.filterRejected },
    { value: "superseded", label: t.prod.approvals.filterSuperseded },
  ];

  return (
    <div className="space-y-4 sm:space-y-5">
      <div className="ui-page-header">
        <div className="min-w-0">
          <h1 className="ui-page-title">{t.prod.approvals.title}</h1>
          <p className="ui-page-subtitle">{t.prod.approvals.subtitle}</p>
        </div>

        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={handleRefresh}
          disabled={isLoading}
          className="min-h-10 w-full gap-1.5 sm:min-h-8 sm:w-auto"
        >
          <RefreshCw className={cn("size-3.5", isLoading && "animate-spin")} />
          <span>{t.common.refresh}</span>
        </Button>
      </div>

      {role !== "director" && (
        <div
          role="status"
          className="ui-notice ui-notice-neutral text-sm text-foreground"
        >
          {t.prod.approvals.readOnlyBanner}
        </div>
      )}

      {error && (
        <Alert variant="destructive" className="ui-notice ui-notice-danger">
          <AlertTriangle className="size-4" />
          <AlertTitle>{t.common.serverErrorTitle}</AlertTitle>
          <AlertDescription className="flex flex-wrap items-center justify-between gap-2 break-words">
            <span>{error}</span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleRefresh}
              className="min-h-10 gap-1.5 sm:min-h-8"
            >
              <RefreshCw className="size-3.5" />
              <span>{t.common.retry}</span>
            </Button>
          </AlertDescription>
        </Alert>
      )}

      {/* Summary KPI strip */}
      <div className="ui-kpi-strip">
        <div className="ui-kpi-cell">
          <span className="ui-kpi-label">{t.director.tiles.pendingLabel}</span>
          <span className="ui-kpi-value">{stats.pendingCount}</span>
        </div>

        <div className="ui-kpi-cell">
          <span className="ui-kpi-label">{t.director.tiles.highRiskLabel}</span>
          <span
            className={cn(
              "ui-kpi-value",
              stats.highRiskCount > 0 && "text-[var(--status-danger-text)]"
            )}
          >
            {stats.highRiskCount}
          </span>
        </div>

        <div className="ui-kpi-cell">
          <span className="ui-kpi-label">{t.director.tiles.resolvedLabel}</span>
          <span className="ui-kpi-value">{stats.resolvedCount}</span>
        </div>

        <div className="ui-kpi-cell">
          <span className="ui-kpi-label">{t.director.tiles.trustedLabel}</span>
          <span className="ui-kpi-value">{stats.trustedCount}</span>
        </div>
      </div>

      {/* Status filter tabs */}
      <div
        role="tablist"
        aria-label={t.prod.approvals.title}
        className="ui-tabs no-scrollbar"
      >
        {filterOptions.map((opt) => {
          const isSelected = statusFilter === opt.value;
          return (
            <button
              key={opt.value}
              type="button"
              role="tab"
              aria-selected={isSelected}
              onClick={() => setStatusFilter(opt.value)}
              className="ui-tab min-h-11 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:min-h-10"
            >
              {opt.label}
            </button>
          );
        })}
      </div>

      {isLoading ? (
        <div className="space-y-4">
          <Skeleton className="h-64 w-full rounded-[8px]" />
          <Skeleton className="h-32 w-full rounded-[8px]" />
        </div>
      ) : approvals.length === 0 ? (
        <div className="ui-panel">
          <div className="ui-empty">
            <div className="ui-empty-title">
              {statusFilter === "all"
                ? t.director.emptyTitle
                : t.prod.approvals.emptyFilteredTitle}
            </div>
            <p className="ui-empty-desc">
              {statusFilter === "all"
                ? t.director.emptyDescription
                : t.prod.approvals.emptyFilteredDescription}
            </p>
            <Link
              href="/payments"
              className={cn(
                buttonVariants({ variant: "outline", size: "sm" }),
                "mt-2 min-h-10 gap-1.5 sm:min-h-8"
              )}
            >
              <ArrowLeft className="size-3.5" />
              <span>{t.director.backToPayments}</span>
            </Link>
          </div>
        </div>
      ) : (
        <ApprovalsList
          approvals={approvals}
          role={role}
          onRefresh={handleRefresh}
        />
      )}
    </div>
  );
}
