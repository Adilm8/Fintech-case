"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ClipboardCheck,
  Inbox,
  Info,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { ApprovalsList } from "@/components/prod/ApprovalsList";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
    <div className="space-y-5 sm:space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold tracking-tight text-foreground sm:text-2xl">
            {t.prod.approvals.title}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {t.prod.approvals.subtitle}
          </p>
        </div>

        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={handleRefresh}
          disabled={isLoading}
          className="min-h-11 w-full gap-1.5 rounded-xl sm:min-h-9 sm:w-auto"
        >
          <RefreshCw className={cn("size-3.5", isLoading && "animate-spin")} />
          <span>{t.common.refresh}</span>
        </Button>
      </div>

      {role !== "director" && (
        <Alert className="rounded-xl border-border bg-muted/60">
          <Info className="size-4" />
          <AlertDescription>{t.prod.approvals.readOnlyBanner}</AlertDescription>
        </Alert>
      )}

      {error && (
        <Alert
          variant="destructive"
          className="rounded-2xl border-red-300 bg-red-50/90"
        >
          <AlertTriangle className="size-4" />
          <AlertTitle>{t.common.serverErrorTitle}</AlertTitle>
          <AlertDescription className="flex flex-wrap items-center justify-between gap-2 break-words">
            <span>{error}</span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleRefresh}
              className="gap-1.5 border-red-300 bg-white text-red-900 hover:bg-red-50"
            >
              <RefreshCw className="size-3.5" />
              <span>{t.common.retry}</span>
            </Button>
          </AlertDescription>
        </Alert>
      )}

      {/* Summary tiles */}
      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <Card className="py-4">
          <CardContent className="flex flex-col justify-between gap-2">
            <div className="flex items-start justify-between gap-2">
              <span className="text-xs font-medium text-muted-foreground sm:text-sm">
                {t.director.tiles.pendingLabel}
              </span>
              <div
                className={cn(
                  "flex size-8 shrink-0 items-center justify-center rounded-xl",
                  stats.pendingCount > 0
                    ? "bg-amber-50 text-amber-700"
                    : "bg-accent text-[var(--brand-text)]"
                )}
              >
                <ClipboardCheck className="size-4" />
              </div>
            </div>
            <div className="text-2xl font-bold tabular-nums text-foreground sm:text-3xl">
              {stats.pendingCount}
            </div>
          </CardContent>
        </Card>

        <Card className="py-4">
          <CardContent className="flex flex-col justify-between gap-2">
            <div className="flex items-start justify-between gap-2">
              <span className="text-xs font-medium text-muted-foreground sm:text-sm">
                {t.director.tiles.highRiskLabel}
              </span>
              <div
                className={cn(
                  "flex size-8 shrink-0 items-center justify-center rounded-xl",
                  stats.highRiskCount > 0
                    ? "bg-red-50 text-red-600"
                    : "bg-muted text-muted-foreground"
                )}
              >
                <AlertTriangle className="size-4" />
              </div>
            </div>
            <div
              className={cn(
                "text-2xl font-bold tabular-nums sm:text-3xl",
                stats.highRiskCount > 0 ? "text-red-700" : "text-foreground"
              )}
            >
              {stats.highRiskCount}
            </div>
          </CardContent>
        </Card>

        <Card className="py-4">
          <CardContent className="flex flex-col justify-between gap-2">
            <div className="flex items-start justify-between gap-2">
              <span className="text-xs font-medium text-muted-foreground sm:text-sm">
                {t.director.tiles.resolvedLabel}
              </span>
              <div className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-muted text-foreground/75">
                <CheckCircle2 className="size-4" />
              </div>
            </div>
            <div className="text-2xl font-bold tabular-nums text-foreground sm:text-3xl">
              {stats.resolvedCount}
            </div>
          </CardContent>
        </Card>

        <Card className="py-4">
          <CardContent className="flex flex-col justify-between gap-2">
            <div className="flex items-start justify-between gap-2">
              <span className="text-xs font-medium text-muted-foreground sm:text-sm">
                {t.director.tiles.trustedLabel}
              </span>
              <div className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-accent text-[var(--brand-text)]">
                <ShieldCheck className="size-4" />
              </div>
            </div>
            <div className="text-2xl font-bold tabular-nums text-foreground sm:text-3xl">
              {stats.trustedCount}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Status filter pills */}
      <div
        role="group"
        aria-label={t.prod.approvals.title}
        className="no-scrollbar -mx-1 flex items-center gap-1.5 overflow-x-auto px-1 pb-0.5 sm:mx-0 sm:flex-wrap sm:px-0"
      >
        {filterOptions.map((opt) => {
          const isSelected = statusFilter === opt.value;
          return (
            <button
              key={opt.value}
              type="button"
              aria-pressed={isSelected}
              onClick={() => setStatusFilter(opt.value)}
              className={cn(
                "inline-flex min-h-10 shrink-0 cursor-pointer items-center rounded-full border px-3.5 py-1 text-xs font-medium transition-all sm:min-h-8",
                isSelected
                  ? "border-primary bg-primary text-primary-foreground font-semibold shadow-xs"
                  : "border-border bg-card text-foreground hover:bg-muted/70"
              )}
            >
              {opt.label}
            </button>
          );
        })}
      </div>

      {isLoading ? (
        <div className="space-y-4">
          <Skeleton className="h-64 w-full rounded-xl" />
          <Skeleton className="h-32 w-full rounded-xl" />
        </div>
      ) : approvals.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center gap-3 py-14 px-4 text-center">
            <div className="flex size-12 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
              <Inbox className="size-6" />
            </div>
            <div className="space-y-1">
              <div className="text-base font-semibold text-foreground">
                {statusFilter === "all"
                  ? t.director.emptyTitle
                  : t.prod.approvals.emptyFilteredTitle}
              </div>
              <p className="max-w-md text-sm text-muted-foreground">
                {statusFilter === "all"
                  ? t.director.emptyDescription
                  : t.prod.approvals.emptyFilteredDescription}
              </p>
            </div>
            <Link
              href="/payments"
              className={cn(
                buttonVariants({ variant: "outline" }),
                "mt-1 min-h-11 gap-2 rounded-xl sm:min-h-9"
              )}
            >
              <ArrowLeft className="size-4" />
              <span>{t.director.backToPayments}</span>
            </Link>
          </CardContent>
        </Card>
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
