"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  AlertTriangle,
  FileSpreadsheet,
  Inbox,
  RefreshCw,
  Search,
  SearchX,
  X,
} from "lucide-react";
import { BatchToolbar } from "@/components/prod/BatchToolbar";
import { ImportDialog } from "@/components/prod/ImportDialog";
import { PaymentForm } from "@/components/prod/PaymentForm";
import { PaymentsTable } from "@/components/prod/PaymentsTable";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useT } from "@/i18n";
import { VERDICT_STYLES } from "@/lib/format";
import { getBatches, getPayments, getProdErrorMessage } from "@/lib/prod/api";
import { useSession } from "@/lib/prod/session";
import type {
  Batch,
  Payment,
  PaymentStatus,
  Verdict,
  VerdictCounts,
} from "@/lib/prod/types";
import { cn } from "cn";

type QueueTab =
  | "to_sign"
  | "pending_approval"
  | "rejected"
  | "postponed"
  | "signed";

const VERDICT_ORDER: readonly Verdict[] = [
  "green",
  "yellow",
  "red",
  "grey",
  "invalid",
] as const;

const EMPTY_VERDICT_COUNTS: VerdictCounts = {
  green: 0,
  yellow: 0,
  red: 0,
  grey: 0,
  invalid: 0,
};

const EMPTY_STATUS_COUNTS: Record<PaymentStatus, number> = {
  checked: 0,
  pending_approval: 0,
  approved: 0,
  rejected: 0,
  postponed: 0,
  signed: 0,
  cancelled: 0,
};

function isEditableElement(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") {
    return true;
  }
  return target.isContentEditable;
}

function PaymentsPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { t, lang, formatDate, interpolate } = useT();
  const { session } = useSession();

  const batchId = searchParams.get("batch_id")?.trim() || null;

  const [activeTab, setActiveTab] = useState<QueueTab>("to_sign");
  const [verdictFilter, setVerdictFilter] = useState<"all" | Verdict>("all");
  const [searchInput, setSearchInput] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");

  const [refreshNonce, setRefreshNonce] = useState(0);
  const fetchKey = `${activeTab}|${batchId ?? ""}|${debouncedQuery}|${lang}|${verdictFilter}|${refreshNonce}`;

  const [loadState, setLoadState] = useState<{
    key: string;
    items: Payment[];
    total: number;
    statusCounts: Record<PaymentStatus, number>;
    verdictCounts: VerdictCounts;
    batchEligibleCounts: { green: number; sendToDirector: number };
    error: string | null;
  } | null>(null);

  const [batchLookup, setBatchLookup] = useState<{
    batchId: string;
    batch: Batch | null;
  } | null>(null);

  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [importDialogOpen, setImportDialogOpen] = useState(false);

  const searchInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedQuery(searchInput.trim());
    }, 250);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (createDialogOpen || importDialogOpen) return;
      if (
        event.key === "/" &&
        !event.ctrlKey &&
        !event.metaKey &&
        !event.altKey &&
        !isEditableElement(event.target)
      ) {
        event.preventDefault();
        searchInputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [createDialogOpen, importDialogOpen]);

  useEffect(() => {
    if (!batchId) return;
    const controller = new AbortController();
    getBatches(50, lang, { signal: controller.signal })
      .then((list) => {
        setBatchLookup({
          batchId,
          batch: list.find((b) => b.id === batchId) ?? null,
        });
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setBatchLookup({ batchId, batch: null });
        }
      });
    return () => controller.abort();
  }, [batchId, lang, refreshNonce]);

  useEffect(() => {
    const controller = new AbortController();

    const isSignedTab = activeTab === "signed";
    const statusParam: PaymentStatus | undefined =
      activeTab === "pending_approval" ||
      activeTab === "rejected" ||
      activeTab === "postponed"
        ? activeTab
        : undefined;

    const listPromise = getPayments(
      {
        scope: isSignedTab ? "signed" : "queue",
        status: statusParam,
        verdict: verdictFilter === "all" ? undefined : verdictFilter,
        batch_id: batchId ?? undefined,
        q: debouncedQuery || undefined,
        limit: 500,
      },
      lang,
      { signal: controller.signal }
    );

    const allCountsPromise = getPayments(
      {
        scope: "all",
        batch_id: batchId ?? undefined,
        limit: 1,
      },
      lang,
      { signal: controller.signal }
    );

    // Fetch checked queue items for accurate batch action button counters.
    const checkedForBatchPromise = getPayments(
      {
        scope: "queue",
        status: "checked",
        batch_id: batchId ?? undefined,
        limit: 500,
      },
      lang,
      { signal: controller.signal }
    );

    Promise.all([listPromise, allCountsPromise, checkedForBatchPromise])
      .then(([listRes, allCountsRes, checkedRes]) => {
        const filteredByTab =
          activeTab === "to_sign"
            ? listRes.items.filter(
                (p) => p.status === "checked" || p.status === "approved"
              )
            : listRes.items;

        let greenChecked = 0;
        let toDirectorChecked = 0;
        for (const p of checkedRes.items) {
          if (p.check.verdict === "green") {
            greenChecked += 1;
          } else if (
            p.check.verdict === "yellow" ||
            p.check.verdict === "red" ||
            p.check.verdict === "grey"
          ) {
            toDirectorChecked += 1;
          }
        }

        setLoadState({
          key: fetchKey,
          items: filteredByTab,
          total:
            activeTab === "to_sign" ? filteredByTab.length : listRes.total,
          verdictCounts: listRes.counts.by_verdict,
          statusCounts: allCountsRes.counts.by_status,
          batchEligibleCounts: {
            green: greenChecked,
            sendToDirector: toDirectorChecked,
          },
          error: null,
        });
      })
      .catch((err) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setLoadState((prev) => ({
          key: fetchKey,
          items: prev?.items ?? [],
          total: prev?.total ?? 0,
          verdictCounts: prev?.verdictCounts ?? EMPTY_VERDICT_COUNTS,
          statusCounts: prev?.statusCounts ?? EMPTY_STATUS_COUNTS,
          batchEligibleCounts: prev?.batchEligibleCounts ?? {
            green: 0,
            sendToDirector: 0,
          },
          error: getProdErrorMessage(err),
        }));
      });

    return () => controller.abort();
  }, [activeTab, batchId, debouncedQuery, fetchKey, lang, verdictFilter]);

  const items = loadState?.items ?? [];
  const total = loadState?.total ?? 0;
  const statusCounts = loadState?.statusCounts ?? EMPTY_STATUS_COUNTS;
  const verdictCounts = loadState?.verdictCounts ?? EMPTY_VERDICT_COUNTS;
  const batchEligibleCounts = loadState?.batchEligibleCounts ?? {
    green: 0,
    sendToDirector: 0,
  };
  const activeBatch =
    batchId && batchLookup?.batchId === batchId ? batchLookup.batch : null;
  const error = loadState?.error ?? null;
  const isLoading = loadState === null || loadState.key !== fetchKey;

  const handleRefresh = useCallback(() => {
    setRefreshNonce((n) => n + 1);
  }, []);

  const tabs: Array<{ key: QueueTab; label: string; count: number }> = useMemo(
    () => [
      {
        key: "to_sign",
        label: t.prod.payments.tabs.toSign,
        count: (statusCounts.checked ?? 0) + (statusCounts.approved ?? 0),
      },
      {
        key: "pending_approval",
        label: t.prod.payments.tabs.pendingApproval,
        count: statusCounts.pending_approval ?? 0,
      },
      {
        key: "rejected",
        label: t.prod.payments.tabs.rejected,
        count: statusCounts.rejected ?? 0,
      },
      {
        key: "postponed",
        label: t.prod.payments.tabs.postponed,
        count: statusCounts.postponed ?? 0,
      },
      {
        key: "signed",
        label: t.prod.payments.tabs.signed,
        count: statusCounts.signed ?? 0,
      },
    ],
    [statusCounts, t.prod.payments.tabs]
  );

  const verdictTotalInScope = useMemo(
    () =>
      VERDICT_ORDER.reduce((sum, v) => sum + (verdictCounts[v] ?? 0), 0),
    [verdictCounts]
  );

  const hasActiveFilters =
    debouncedQuery.length > 0 || verdictFilter !== "all";

  const resetFilters = () => {
    setSearchInput("");
    setDebouncedQuery("");
    setVerdictFilter("all");
  };

  const role = session?.user.role ?? "analyst";

  return (
    <div className="space-y-5 sm:space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold tracking-tight text-foreground sm:text-2xl">
            {t.prod.payments.title}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {t.prod.payments.subtitle}
          </p>
        </div>

        <BatchToolbar
          role={role}
          batchId={batchId}
          greenCount={batchEligibleCounts.green}
          sendToDirectorCount={batchEligibleCounts.sendToDirector}
          showBatchActions={activeTab !== "signed"}
          onNewPayment={() => setCreateDialogOpen(true)}
          onOpenImport={() => setImportDialogOpen(true)}
          onBatchCompleted={handleRefresh}
        />
      </div>

      {batchId && (
        <div className="flex flex-col gap-3 rounded-2xl border border-primary/30 bg-accent/55 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 items-start gap-2.5">
            <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary/15 text-[var(--brand-text)]">
              <FileSpreadsheet className="size-4" />
            </div>
            <div className="min-w-0">
              <div className="text-sm font-semibold text-foreground break-all">
                {activeBatch
                  ? interpolate(t.prod.payments.batchFilterTitle, {
                      filename: activeBatch.filename,
                    })
                  : interpolate(t.prod.payments.batchFilterFallback, {
                      id: batchId,
                    })}
              </div>
              {activeBatch && (
                <div className="text-xs text-muted-foreground">
                  {interpolate(t.prod.payments.batchFilterMeta, {
                    source: activeBatch.source.toUpperCase(),
                    date: formatDate(activeBatch.created_at),
                    created: activeBatch.created_count,
                    total: activeBatch.total,
                  })}
                </div>
              )}
            </div>
          </div>

          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => router.push("/payments")}
            className="min-h-10 shrink-0 gap-1.5 rounded-xl bg-card sm:min-h-8"
          >
            <X className="size-3.5" />
            <span>{t.prod.payments.clearBatchFilter}</span>
          </Button>
        </div>
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

      {/* Status tabs */}
      <div
        role="tablist"
        aria-label={t.prod.payments.title}
        className="no-scrollbar -mx-1 flex items-center gap-1.5 overflow-x-auto px-1 pb-0.5 sm:mx-0 sm:flex-wrap sm:px-0"
      >
        {tabs.map((tab) => {
          const isSelected = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              type="button"
              role="tab"
              aria-selected={isSelected}
              onClick={() => {
                setActiveTab(tab.key);
                setVerdictFilter("all");
              }}
              className={cn(
                "inline-flex min-h-11 shrink-0 cursor-pointer items-center gap-2 rounded-xl border px-3.5 py-2 text-sm transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:min-h-9 sm:py-1.5",
                isSelected
                  ? "border-primary bg-primary text-primary-foreground font-semibold shadow-xs"
                  : "border-border bg-card text-foreground font-medium hover:bg-muted/70"
              )}
            >
              <span>{tab.label}</span>
              <span
                className={cn(
                  "rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums leading-none",
                  isSelected
                    ? "bg-white/20 text-white"
                    : "bg-muted text-muted-foreground"
                )}
              >
                {tab.count}
              </span>
            </button>
          );
        })}
      </div>

      {/* Main queue card */}
      <Card className="min-w-0 py-0">
        <div className="border-b border-border p-4 space-y-3 sm:px-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="relative flex-1 sm:max-w-md">
              <Search
                aria-hidden="true"
                className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
              />
              <Input
                ref={searchInputRef}
                type="search"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Escape") {
                    if (searchInput) {
                      e.preventDefault();
                      setSearchInput("");
                      setDebouncedQuery("");
                    } else {
                      e.currentTarget.blur();
                    }
                  }
                }}
                placeholder={t.prod.payments.searchPlaceholder}
                aria-label={t.prod.payments.searchAriaLabel}
                className="h-11 rounded-xl bg-background/70 pl-9 pr-10 sm:h-10 [&::-webkit-search-cancel-button]:hidden"
              />
              {searchInput ? (
                <button
                  type="button"
                  onClick={() => {
                    setSearchInput("");
                    setDebouncedQuery("");
                    searchInputRef.current?.focus();
                  }}
                  aria-label={t.queue.clearSearch}
                  className="absolute top-1/2 right-1.5 flex size-8 -translate-y-1/2 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                >
                  <X className="size-4" />
                </button>
              ) : (
                <kbd
                  aria-hidden="true"
                  className="pointer-events-none absolute top-1/2 right-2.5 hidden -translate-y-1/2 items-center justify-center rounded-md border border-border bg-card px-1.5 py-0.5 font-mono text-[11px] font-medium text-muted-foreground sm:inline-flex"
                >
                  /
                </kbd>
              )}
            </div>

            <div className="flex items-center justify-between gap-2 sm:justify-end">
              <span className="text-xs font-medium text-muted-foreground tabular-nums">
                {interpolate(t.prod.payments.totalInScope, { count: total })}
              </span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleRefresh}
                disabled={isLoading}
                className="min-h-9 gap-1.5 rounded-xl"
              >
                <RefreshCw
                  className={cn("size-3.5", isLoading && "animate-spin")}
                />
                <span>{t.common.refresh}</span>
              </Button>
            </div>
          </div>

          {/* Traffic-light counters from counts.by_verdict */}
          <div
            role="group"
            aria-label={t.queue.filtersAriaLabel}
            className="no-scrollbar -mx-1 flex items-center gap-1.5 overflow-x-auto px-1 py-0.5 sm:mx-0 sm:flex-wrap sm:overflow-visible sm:px-0"
          >
            <button
              type="button"
              aria-pressed={verdictFilter === "all"}
              onClick={() => setVerdictFilter("all")}
              className={cn(
                "inline-flex min-h-10 shrink-0 cursor-pointer items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:min-h-8",
                verdictFilter === "all"
                  ? "border-primary bg-primary text-primary-foreground shadow-xs"
                  : "border-border bg-card text-foreground hover:bg-muted/70"
              )}
            >
              <span>{t.queue.filterAll}</span>
              <span
                className={cn(
                  "rounded-full px-1.5 py-0.5 text-[11px] font-semibold tabular-nums leading-none",
                  verdictFilter === "all"
                    ? "bg-white/20 text-white"
                    : "bg-muted text-muted-foreground"
                )}
              >
                {verdictTotalInScope}
              </span>
            </button>

            {VERDICT_ORDER.map((verdict) => {
              const count = verdictCounts[verdict] ?? 0;
              const isSelected = verdictFilter === verdict;
              const style = VERDICT_STYLES[verdict];
              return (
                <button
                  key={verdict}
                  type="button"
                  aria-pressed={isSelected}
                  onClick={() =>
                    setVerdictFilter((prev) =>
                      prev === verdict ? "all" : verdict
                    )
                  }
                  className={cn(
                    "inline-flex min-h-10 shrink-0 cursor-pointer items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:min-h-8",
                    isSelected
                      ? cn(
                          style.badgeClass,
                          "font-semibold shadow-xs ring-1 ring-current/25"
                        )
                      : "border-border bg-card text-foreground hover:bg-muted/70"
                  )}
                >
                  <span
                    aria-hidden="true"
                    className={cn("size-2 shrink-0 rounded-full", style.dotClass)}
                  />
                  <span>{t.verdicts[verdict]}</span>
                  <span
                    className={cn(
                      "rounded-full px-1.5 py-0.5 text-[11px] font-semibold tabular-nums leading-none",
                      isSelected
                        ? "bg-white/70 text-current"
                        : "bg-muted text-muted-foreground"
                    )}
                  >
                    {count}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        <CardContent className="p-0">
          {isLoading ? (
            <div className="space-y-3 p-4">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-16 w-full rounded-xl" />
              ))}
            </div>
          ) : items.length === 0 ? (
            hasActiveFilters ? (
              <div className="flex flex-col items-center justify-center gap-3 py-14 px-4 text-center">
                <div className="flex size-12 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
                  <SearchX className="size-6" />
                </div>
                <div className="space-y-1">
                  <div className="text-base font-semibold text-foreground">
                    {t.queue.emptyFilteredTitle}
                  </div>
                  <p className="max-w-md text-sm text-muted-foreground">
                    {t.queue.emptyFilteredDescription}
                  </p>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  onClick={resetFilters}
                  className="mt-1 min-h-11 rounded-xl sm:min-h-9"
                >
                  {t.queue.resetFilters}
                </Button>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center gap-3 py-16 px-4 text-center">
                <div className="flex size-12 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
                  <Inbox className="size-6" />
                </div>
                <div className="space-y-1">
                  <div className="text-base font-semibold text-foreground">
                    {t.prod.payments.emptyTabTitle}
                  </div>
                  <p className="max-w-md text-sm text-muted-foreground">
                    {role === "accountant"
                      ? t.prod.payments.emptyTabDescription
                      : t.prod.payments.emptyReadOnlyDescription}
                  </p>
                </div>
              </div>
            )
          ) : (
            <PaymentsTable payments={items} />
          )}
        </CardContent>
      </Card>

      {role === "accountant" && (
        <>
          <PaymentForm
            open={createDialogOpen}
            onOpenChange={setCreateDialogOpen}
            mode="create"
            onSaved={handleRefresh}
          />
          <ImportDialog
            open={importDialogOpen}
            onOpenChange={setImportDialogOpen}
            onImported={handleRefresh}
          />
        </>
      )}
    </div>
  );
}

export default function ProdPaymentsPage() {
  return (
    <Suspense
      fallback={
        <div className="space-y-4">
          <Skeleton className="h-9 w-56" />
          <Skeleton className="h-12 w-full rounded-xl" />
          <Skeleton className="h-72 w-full rounded-xl" />
        </div>
      }
    >
      <PaymentsPageContent />
    </Suspense>
  );
}
