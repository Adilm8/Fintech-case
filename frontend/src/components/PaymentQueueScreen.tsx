"use client";

import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { ChevronDown, ChevronRight, Search, X } from "lucide-react";
import { NewPaymentDialog } from "@/components/NewPaymentDialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { VerdictBadge } from "@/components/VerdictBadge";
import { useT } from "@/i18n";
import {
  APPROVAL_STATUS_STYLES,
  findApprovalForPayment,
} from "@/lib/approvals";
import { pickReason, VERDICT_STYLES } from "@/lib/format";
import {
  getQueuePreferencesSnapshot,
  getServerQueuePreferencesSnapshot,
  subscribeQueuePreferences,
  updateQueuePreferences,
  type QueueSort,
  type VerdictFilter,
} from "@/lib/preferences";
import type {
  Approval,
  ApprovalStatus,
  CheckRequest,
  CheckResult,
  QueueItem,
  Verdict,
} from "@/lib/types";
import { cn } from "cn";

interface PaymentQueueScreenProps {
  queue: QueueItem[];
  approvals: Approval[];
  approvalsError?: boolean;
  isLoading: boolean;
  hasError?: boolean;
  prefillRequest?: CheckRequest | null;
  openNewInitially?: boolean;
  onConsumeOpenNew?: () => void;
  onClearPrefill?: () => void;
  onSelectPayment: (item: QueueItem) => void;
  onSelectPaymentById?: (id: string) => void;
  onAddQueueItem: (request: CheckRequest, result: CheckResult) => string;
  onRefreshQueue: () => Promise<void> | void;
  onNetworkError: (message: string) => void;
}

const VERDICT_ORDER: readonly Verdict[] = [
  "green",
  "yellow",
  "red",
  "grey",
  "invalid",
] as const;

const RISK_PRIORITY: Record<Verdict, number> = {
  red: 0,
  invalid: 1,
  yellow: 2,
  grey: 3,
  green: 4,
};

const APPROVAL_DOT_CLASS: Record<ApprovalStatus, string> = {
  pending: "ui-dot-warn",
  approved: "ui-dot-ok",
  rejected: "ui-dot-danger",
};

/**
 * Counts payments requiring accountant/director attention before signing.
 * Every non-green verdict needs review:
 * - red: likely spoofing / blocking risk (signing blocked without director)
 * - invalid: checksum/format error in requisites (cannot be signed)
 * - yellow: requisite or amount changes compared to history
 * - grey: first payment to a new supplier with no history to compare against
 */
function needsAttention(verdict: Verdict): boolean {
  return verdict !== "green";
}

function isAtRiskVerdict(verdict: Verdict): boolean {
  return verdict === "red" || verdict === "yellow" || verdict === "invalid";
}

function matchesSearchQuery(item: QueueItem, rawQuery: string): boolean {
  const trimmed = rawQuery.trim().toLowerCase();
  if (!trimmed) return true;

  const compact = trimmed.replace(/\s+/g, "");
  const name = item.request.recipient_name.toLowerCase();
  const bin = item.request.recipient_bin.replace(/\s+/g, "").toLowerCase();
  const iik = item.request.recipient_iik.replace(/\s+/g, "").toLowerCase();

  return (
    name.includes(trimmed) ||
    bin.includes(compact) ||
    iik.includes(compact)
  );
}

function isEditableElement(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") {
    return true;
  }
  return target.isContentEditable;
}

export function PaymentQueueScreen({
  queue,
  approvals,
  approvalsError = false,
  isLoading,
  hasError = false,
  prefillRequest,
  openNewInitially = false,
  onConsumeOpenNew,
  onClearPrefill,
  onSelectPayment,
  onSelectPaymentById,
  onAddQueueItem,
  onRefreshQueue,
  onNetworkError,
}: PaymentQueueScreenProps) {
  const { t, lang, mounted, formatMoney, interpolate } = useT();

  const storedPrefs = useSyncExternalStore(
    subscribeQueuePreferences,
    getQueuePreferencesSnapshot,
    getServerQueuePreferencesSnapshot
  );
  const prefs = mounted ? storedPrefs : getServerQueuePreferencesSnapshot();
  const searchQuery = prefs.searchQuery;
  const verdictFilter = prefs.verdictFilter;
  const sortOrder = prefs.sort;

  const setSearchQuery = (next: string) => {
    updateQueuePreferences({ searchQuery: next });
  };
  const setVerdictFilter = (
    next: VerdictFilter | ((prev: VerdictFilter) => VerdictFilter)
  ) => {
    updateQueuePreferences((prev) => ({
      ...prev,
      verdictFilter:
        typeof next === "function" ? next(prev.verdictFilter) : next,
    }));
  };
  const setSortOrder = (next: QueueSort) => {
    updateQueuePreferences({ sort: next });
  };

  const [dialogOpen, setDialogOpen] = useState(openNewInitially);
  const [highlightedId, setHighlightedId] = useState<string | null>(null);

  const searchInputRef = useRef<HTMLInputElement>(null);
  const rowRefs = useRef<Map<string, HTMLElement>>(new Map());

  const isDialogOpen = dialogOpen || Boolean(prefillRequest);

  useEffect(() => {
    if (openNewInitially) {
      onConsumeOpenNew?.();
    }
  }, [openNewInitially, onConsumeOpenNew]);

  useEffect(() => {
    const handleOpenNewEvent = () => {
      setDialogOpen(true);
    };
    window.addEventListener(
      "business-shield:open-new-payment",
      handleOpenNewEvent
    );
    return () => {
      window.removeEventListener(
        "business-shield:open-new-payment",
        handleOpenNewEvent
      );
    };
  }, []);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (isDialogOpen) return;
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      if (isEditableElement(event.target)) return;
      if (document.querySelector('[data-slot="dialog-content"]')) return;

      if (event.key === "/") {
        event.preventDefault();
        searchInputRef.current?.focus();
      } else if (
        !event.shiftKey &&
        (event.key.toLowerCase() === "n" || event.code === "KeyN")
      ) {
        event.preventDefault();
        setDialogOpen(true);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isDialogOpen]);

  useEffect(() => {
    if (!highlightedId) return;
    const rafId = window.requestAnimationFrame(() => {
      const mobileEl = rowRefs.current.get(`mobile:${highlightedId}`);
      const desktopEl = rowRefs.current.get(`desktop:${highlightedId}`);
      const target =
        mobileEl && mobileEl.offsetParent !== null
          ? mobileEl
          : desktopEl && desktopEl.offsetParent !== null
            ? desktopEl
            : mobileEl ?? desktopEl;
      if (target) {
        target.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
    });
    const timer = window.setTimeout(() => {
      setHighlightedId(null);
    }, 3500);
    return () => {
      window.cancelAnimationFrame(rafId);
      window.clearTimeout(timer);
    };
  }, [highlightedId]);

  const verdictCounts = useMemo(() => {
    const counts: Record<Verdict, number> = {
      green: 0,
      yellow: 0,
      red: 0,
      grey: 0,
      invalid: 0,
    };
    for (const item of queue) {
      if (item.result.verdict in counts) {
        counts[item.result.verdict] += 1;
      }
    }
    return counts;
  }, [queue]);

  const availableVerdicts = useMemo(
    () =>
      VERDICT_ORDER.filter(
        (verdict) => verdictCounts[verdict] > 0 || verdictFilter === verdict
      ),
    [verdictCounts, verdictFilter]
  );

  const readyToSignCount = verdictCounts.green;

  const attentionCount = useMemo(
    () => queue.filter((item) => needsAttention(item.result.verdict)).length,
    [queue]
  );

  const pendingApprovalsCount = useMemo(
    () => approvals.filter((item) => item.status === "pending").length,
    [approvals]
  );

  const atRiskSummary = useMemo(() => {
    let count = 0;
    let amount = 0;
    for (const item of queue) {
      if (isAtRiskVerdict(item.result.verdict)) {
        count += 1;
        amount += item.request.amount_kzt || 0;
      }
    }
    return { count, amount };
  }, [queue]);

  const filteredQueue = useMemo(() => {
    const filtered = queue.filter((item) => {
      if (verdictFilter !== "all" && item.result.verdict !== verdictFilter) {
        return false;
      }
      return matchesSearchQuery(item, searchQuery);
    });

    if (sortOrder === "default") {
      return filtered;
    }

    const locale = lang === "en" ? "en" : lang === "kk" ? "kk" : "ru";
    return [...filtered].sort((a, b) => {
      if (sortOrder === "risk_desc") {
        const rankDiff =
          (RISK_PRIORITY[a.result.verdict] ?? 9) -
          (RISK_PRIORITY[b.result.verdict] ?? 9);
        if (rankDiff !== 0) return rankDiff;
        if (b.result.score !== a.result.score) {
          return b.result.score - a.result.score;
        }
        return (b.request.amount_kzt || 0) - (a.request.amount_kzt || 0);
      }
      if (sortOrder === "amount_desc") {
        return (b.request.amount_kzt || 0) - (a.request.amount_kzt || 0);
      }
      if (sortOrder === "amount_asc") {
        return (a.request.amount_kzt || 0) - (b.request.amount_kzt || 0);
      }
      if (sortOrder === "name_asc") {
        return a.request.recipient_name.localeCompare(
          b.request.recipient_name,
          locale,
          { sensitivity: "base" }
        );
      }
      return 0;
    });
  }, [queue, verdictFilter, searchQuery, sortOrder, lang]);

  const hasActiveFilters =
    searchQuery.trim().length > 0 || verdictFilter !== "all";

  const resetFilters = () => {
    updateQueuePreferences((prev) => ({
      ...prev,
      searchQuery: "",
      verdictFilter: "all",
    }));
  };

  const handleDialogOpenChange = (nextOpen: boolean) => {
    setDialogOpen(nextOpen);
    if (!nextOpen && prefillRequest) {
      onClearPrefill?.();
    }
  };

  const handlePaymentCreated = (
    request: CheckRequest,
    result: CheckResult
  ): string => {
    if (prefillRequest) {
      onClearPrefill?.();
    }
    const addedId = onAddQueueItem(request, result);
    if (
      verdictFilter !== "all" &&
      verdictFilter !== result.verdict
    ) {
      setVerdictFilter("all");
    }
    if (searchQuery.trim()) {
      setSearchQuery("");
    }
    setHighlightedId(addedId);
    void onRefreshQueue();
    return addedId;
  };

  const registerRowRef = (id: string, node: HTMLElement | null) => {
    if (node) {
      rowRefs.current.set(id, node);
    } else {
      rowRefs.current.delete(id);
    }
  };

  return (
    <div className="space-y-4 sm:space-y-5">
      <div className="ui-page-header">
        <div className="min-w-0">
          <h1 className="ui-page-title">{t.queue.title}</h1>
          <p className="ui-page-subtitle">{t.queue.description}</p>
        </div>

        <Tooltip>
          <TooltipTrigger
            render={
              <Button
                type="button"
                onClick={() => setDialogOpen(true)}
                className="min-h-10 w-full sm:min-h-9 sm:w-auto"
              />
            }
          >
            <span>{t.queue.addPaymentButton}</span>
            <kbd
              aria-hidden="true"
              className="ml-0.5 hidden rounded-[4px] border border-white/30 bg-white/15 px-1.5 py-0.5 font-mono text-[10px] font-medium leading-none text-white sm:inline-flex"
            >
              N
            </kbd>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            {t.queue.newPaymentTooltip}
          </TooltipContent>
        </Tooltip>
      </div>

      {/* Summary strip: 2 columns on phone, 4 on desktop */}
      <div className="ui-kpi-strip">
        {isLoading && queue.length === 0 ? (
          Array.from({ length: 4 }).map((_, index) => (
            <div key={`tile-skeleton-${index}`} className="ui-kpi-cell">
              <Skeleton className="h-3.5 w-24 rounded-[4px]" />
              <Skeleton className="h-6 w-16 rounded-[4px]" />
              <Skeleton className="h-3 w-28 rounded-[4px]" />
            </div>
          ))
        ) : (
          <>
            <button
              type="button"
              onClick={resetFilters}
              className="ui-kpi-cell cursor-pointer transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
            >
              <span className="ui-kpi-label">
                {t.queue.tiles.totalPaymentsLabel}
              </span>
              <div className="ui-kpi-value">{queue.length}</div>
              <div className="text-xs text-muted-foreground">
                {interpolate(t.queue.tiles.readyToSignHint, {
                  count: readyToSignCount,
                })}
              </div>
            </button>

            <div className="ui-kpi-cell">
              <span className="ui-kpi-label">
                {t.queue.tiles.needsReviewLabel}
              </span>
              <div
                className={cn(
                  "ui-kpi-value",
                  attentionCount > 0 && "text-[var(--status-warn-text)]"
                )}
              >
                {attentionCount}
              </div>
              <div className="text-xs text-muted-foreground">
                {attentionCount > 0
                  ? t.queue.tiles.needsAttentionHint
                  : t.queue.tiles.allClearHint}
              </div>
            </div>

            <Link
              href="/approvals"
              className="ui-kpi-cell transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
            >
              <span className="ui-kpi-label">
                {t.queue.tiles.pendingApprovalsLabel}
              </span>
              <div className="ui-kpi-value">
                {approvalsError ? "—" : pendingApprovalsCount}
              </div>
              <div className="text-xs font-medium text-[var(--brand-text)]">
                {approvalsError
                  ? t.queue.tiles.pendingApprovalsUnavailable
                  : t.queue.tiles.pendingApprovalsHint}
              </div>
            </Link>

            <div className="ui-kpi-cell">
              <span className="ui-kpi-label">
                {t.queue.tiles.amountAtRiskLabel}
              </span>
              <div
                className={cn(
                  "ui-kpi-value truncate whitespace-nowrap",
                  atRiskSummary.amount > 0 &&
                    "text-[var(--status-danger-text)]"
                )}
              >
                {formatMoney(atRiskSummary.amount)}
              </div>
              <div className="text-xs text-muted-foreground">
                {atRiskSummary.count > 0
                  ? interpolate(t.queue.tiles.amountAtRiskHint, {
                      count: atRiskSummary.count,
                    })
                  : t.queue.tiles.allClearHint}
              </div>
            </div>
          </>
        )}
      </div>

      {/* Main Queue Panel */}
      <Card className="min-w-0 py-0">
        {/* Toolbar: Search + Sort + Verdict Chips */}
        <div className="space-y-3 border-b border-border p-4">
          {isLoading && queue.length === 0 ? (
            <div className="space-y-3">
              <Skeleton className="h-9 w-full max-w-md rounded-[6px]" />
              <div className="flex flex-wrap gap-1.5">
                <Skeleton className="h-8 w-20 rounded-[6px]" />
                <Skeleton className="h-8 w-28 rounded-[6px]" />
                <Skeleton className="h-8 w-28 rounded-[6px]" />
                <Skeleton className="h-8 w-32 rounded-[6px]" />
              </div>
            </div>
          ) : (
            <>
              <div className="flex flex-col gap-2.5 sm:flex-row sm:items-center sm:justify-between">
                <div className="relative flex-1 sm:max-w-md">
                  <Search
                    aria-hidden="true"
                    className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
                  />
                  <Input
                    ref={searchInputRef}
                    type="search"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Escape") {
                        if (searchQuery) {
                          e.preventDefault();
                          setSearchQuery("");
                        } else {
                          e.currentTarget.blur();
                        }
                      }
                    }}
                    placeholder={t.queue.searchPlaceholder}
                    aria-label={t.queue.searchAriaLabel}
                    title={t.queue.searchTooltip}
                    className="h-10 rounded-[6px] bg-card pl-9 pr-10 sm:h-9 [&::-webkit-search-cancel-button]:hidden"
                  />
                  {searchQuery ? (
                    <button
                      type="button"
                      onClick={() => {
                        setSearchQuery("");
                        searchInputRef.current?.focus();
                      }}
                      aria-label={t.queue.clearSearch}
                      className="absolute top-1/2 right-1.5 flex size-8 -translate-y-1/2 items-center justify-center rounded-[4px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      <X className="size-4" />
                    </button>
                  ) : (
                    <Tooltip>
                      <TooltipTrigger
                        render={
                          <kbd
                            aria-hidden="true"
                            className="absolute top-1/2 right-2.5 hidden -translate-y-1/2 cursor-default items-center justify-center rounded-[4px] border border-border bg-muted px-1.5 py-0.5 font-mono text-[11px] font-medium text-muted-foreground sm:inline-flex"
                          />
                        }
                      >
                        /
                      </TooltipTrigger>
                      <TooltipContent side="top">
                        {t.queue.searchTooltip}
                      </TooltipContent>
                    </Tooltip>
                  )}
                </div>

                <div className="flex flex-wrap items-center justify-between gap-2.5 sm:justify-end">
                  <div className="relative flex-1 sm:flex-initial">
                    <select
                      aria-label={t.queue.sortLabel}
                      value={sortOrder}
                      onChange={(e) =>
                        setSortOrder(e.target.value as QueueSort)
                      }
                      className="ui-select h-10 w-full appearance-none sm:h-9 sm:w-auto"
                    >
                      <option value="default">
                        {t.queue.sortOptions.default}
                      </option>
                      <option value="risk_desc">
                        {t.queue.sortOptions.risk_desc}
                      </option>
                      <option value="amount_desc">
                        {t.queue.sortOptions.amount_desc}
                      </option>
                      <option value="amount_asc">
                        {t.queue.sortOptions.amount_asc}
                      </option>
                      <option value="name_asc">
                        {t.queue.sortOptions.name_asc}
                      </option>
                    </select>
                    <ChevronDown
                      aria-hidden="true"
                      className="pointer-events-none absolute top-1/2 right-2.5 size-3.5 -translate-y-1/2 text-muted-foreground"
                    />
                  </div>

                  <div className="text-xs font-medium text-muted-foreground tabular-nums">
                    {hasError && queue.length === 0
                      ? t.common.noServerConnection
                      : hasActiveFilters
                        ? interpolate(t.queue.shownOfTotal, {
                            shown: filteredQueue.length,
                            total: queue.length,
                          })
                        : interpolate(t.queue.totalInQueue, {
                            count: queue.length,
                          })}
                  </div>
                </div>
              </div>

              {queue.length > 0 && (
                <div
                  role="group"
                  aria-label={t.queue.filtersAriaLabel}
                  className="no-scrollbar -mx-1 flex items-center gap-1.5 overflow-x-auto px-1 py-0.5 sm:mx-0 sm:flex-wrap sm:overflow-visible sm:px-0"
                >
                  <button
                    type="button"
                    aria-pressed={verdictFilter === "all"}
                    onClick={() => setVerdictFilter("all")}
                    className="ui-filter-chip focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <span>{t.queue.filterAll}</span>
                    <span className="tabular-nums text-muted-foreground">
                      {queue.length}
                    </span>
                  </button>

                  {availableVerdicts.map((verdict) => {
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
                        className="ui-filter-chip focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      >
                        <span
                          aria-hidden="true"
                          className={cn("ui-status-dot", style.dotClass)}
                        />
                        <span>{t.verdicts[verdict]}</span>
                        <span className="tabular-nums text-muted-foreground">
                          {verdictCounts[verdict]}
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}
            </>
          )}
        </div>

        <CardContent className="p-0">
          {isLoading && queue.length === 0 ? (
            <>
              {/* Phone skeleton list */}
              <div className="divide-y divide-border md:hidden">
                {Array.from({ length: 4 }).map((_, index) => (
                  <div
                    key={`card-skeleton-${index}`}
                    className="space-y-2 p-4"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <Skeleton className="h-4 w-44 rounded-[4px]" />
                      <Skeleton className="h-4 w-24 rounded-[4px]" />
                    </div>
                    <Skeleton className="h-5 w-32 rounded-[4px]" />
                    <Skeleton className="h-3.5 w-56 rounded-[4px]" />
                    <Skeleton className="h-4 w-full rounded-[4px]" />
                  </div>
                ))}
              </div>

              {/* Desktop skeleton table */}
              <div className="hidden md:block">
                <Table>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent">
                      <TableHead className="pl-4">
                        {t.queue.colRecipient}
                      </TableHead>
                      <TableHead className="text-right">
                        {t.queue.colAmount}
                      </TableHead>
                      <TableHead>{t.queue.colPurpose}</TableHead>
                      <TableHead className="whitespace-normal">
                        {t.queue.colCheckResult}
                      </TableHead>
                      <TableHead className="w-9 pr-3" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {Array.from({ length: 5 }).map((_, index) => (
                      <TableRow
                        key={`row-skeleton-${index}`}
                        className="hover:bg-transparent"
                      >
                        <TableCell className="pl-4 py-3">
                          <div className="space-y-1.5">
                            <Skeleton className="h-4 w-48 rounded-[4px]" />
                            <Skeleton className="h-3 w-64 rounded-[4px]" />
                          </div>
                        </TableCell>
                        <TableCell className="py-3">
                          <Skeleton className="ml-auto h-4 w-24 rounded-[4px]" />
                        </TableCell>
                        <TableCell className="py-3">
                          <Skeleton className="h-4 w-44 rounded-[4px]" />
                        </TableCell>
                        <TableCell className="py-3">
                          <Skeleton className="h-4 w-28 rounded-[4px]" />
                        </TableCell>
                        <TableCell className="pr-3 py-3">
                          <Skeleton className="ml-auto size-4 rounded-[4px]" />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </>
          ) : hasError && queue.length === 0 ? (
            <div className="ui-empty">
              <div className="ui-empty-title">{t.common.serverErrorTitle}</div>
              <p className="ui-empty-desc">{t.queue.loadErrorEmpty}</p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => void onRefreshQueue()}
                className="mt-2 min-h-10 sm:min-h-8"
              >
                {t.common.retry}
              </Button>
            </div>
          ) : queue.length === 0 ? (
            <div className="ui-empty">
              <div className="ui-empty-title">{t.queue.emptyTitle}</div>
              <p className="ui-empty-desc">{t.queue.emptyQueue}</p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setDialogOpen(true)}
                className="mt-2 min-h-10 sm:min-h-8"
              >
                {t.queue.addPaymentButton}
              </Button>
            </div>
          ) : filteredQueue.length === 0 ? (
            <div className="ui-empty">
              <div className="ui-empty-title">{t.queue.emptyFilteredTitle}</div>
              <p className="ui-empty-desc">
                {t.queue.emptyFilteredDescription}
              </p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={resetFilters}
                className="mt-2 min-h-10 sm:min-h-8"
              >
                {t.queue.resetFilters}
              </Button>
            </div>
          ) : (
            <>
              {/* Mobile flat list (< md) */}
              <div className="divide-y divide-border md:hidden">
                {filteredQueue.map((item) => {
                  const approval = findApprovalForPayment(
                    approvals,
                    item.request
                  );
                  const approvalStyle = approval
                    ? APPROVAL_STATUS_STYLES[approval.status]
                    : null;
                  const approvalLabel = approval
                    ? t.approvalStatus[approval.status]
                    : null;
                  const directorComment = approval?.director_comment?.trim();
                  const firstSignal = item.result.signals[0];
                  const primaryReason = firstSignal
                    ? pickReason(firstSignal, lang).trim()
                    : "";
                  const isHighlighted = highlightedId === item.id;

                  return (
                    <button
                      key={item.id}
                      ref={(node) => registerRowRef(`mobile:${item.id}`, node)}
                      type="button"
                      onClick={() => onSelectPayment(item)}
                      className={cn(
                        "block w-full min-h-11 px-4 py-3 text-left transition-colors hover:bg-muted/40 active:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
                        isHighlighted && "bg-[var(--brand-subtle)]"
                      )}
                    >
                      <div className="flex items-start justify-between gap-2.5">
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-1.5">
                            <span className="text-sm font-semibold leading-5 text-foreground break-words">
                              {item.request.recipient_name}
                            </span>
                            {isHighlighted && (
                              <span className="ui-tag">
                                {t.queue.newBadge}
                              </span>
                            )}
                          </div>
                        </div>
                        <VerdictBadge
                          verdict={item.result.verdict}
                          label={
                            item.result.verdict === "green" &&
                            item.result.signals.some(
                              (s) => s.rule_id === "budget_payment"
                            )
                              ? t.signalRules.budget_payment
                              : undefined
                          }
                          className="shrink-0"
                        />
                      </div>

                      {primaryReason && (
                        <p
                          title={primaryReason}
                          className="mt-1 truncate text-xs leading-4 text-[var(--text-secondary)]"
                        >
                          {primaryReason}
                        </p>
                      )}

                      <div className="mt-1.5 flex items-center justify-between gap-2">
                        <div className="text-base font-semibold tabular-nums whitespace-nowrap text-foreground">
                          {formatMoney(item.request.amount_kzt)}
                        </div>
                        <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
                      </div>

                      <div className="mt-1 flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5 font-mono text-xs tabular-nums text-muted-foreground">
                        <span>
                          {interpolate(t.common.binPrefix, {
                            bin: item.request.recipient_bin,
                          })}
                        </span>
                        <span aria-hidden="true">·</span>
                        <span className="break-all">
                          {item.request.recipient_iik}
                        </span>
                      </div>

                      <p className="mt-1.5 line-clamp-2 text-[13px] text-[var(--text-secondary)] break-words">
                        {item.request.purpose}
                      </p>

                      {(approval || directorComment) && (
                        <div className="mt-2 flex flex-col items-start gap-1 border-t border-border pt-2">
                          {approval && approvalStyle && approvalLabel && (
                            <span
                              className={cn(
                                "ui-status",
                                approvalStyle.badgeClass
                              )}
                            >
                              <span
                                aria-hidden="true"
                                className={cn(
                                  "ui-status-dot",
                                  APPROVAL_DOT_CLASS[approval.status]
                                )}
                              />
                              <span>{approvalLabel}</span>
                            </span>
                          )}
                          {directorComment && (
                            <p className="line-clamp-2 text-xs text-muted-foreground break-words">
                              {interpolate(t.queue.directorPrefix, {
                                comment: directorComment,
                              })}
                            </p>
                          )}
                        </div>
                      )}
                    </button>
                  );
                })}
              </div>

              {/* Desktop table (>= md) */}
              <div className="hidden md:block">
                <Table>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent">
                      <TableHead className="pl-4">
                        {t.queue.colRecipient}
                      </TableHead>
                      <TableHead className="text-right">
                        {t.queue.colAmount}
                      </TableHead>
                      <TableHead>{t.queue.colPurpose}</TableHead>
                      <TableHead className="whitespace-normal">
                        {t.queue.colCheckResult}
                      </TableHead>
                      <TableHead className="w-9 pr-3" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredQueue.map((item) => {
                      const approval = findApprovalForPayment(
                        approvals,
                        item.request
                      );
                      const approvalStyle = approval
                        ? APPROVAL_STATUS_STYLES[approval.status]
                        : null;
                      const approvalLabel = approval
                        ? t.approvalStatus[approval.status]
                        : null;
                      const directorComment =
                        approval?.director_comment?.trim();
                      const firstSignal = item.result.signals[0];
                      const primaryReason = firstSignal
                        ? pickReason(firstSignal, lang).trim()
                        : "";
                      const isHighlighted = highlightedId === item.id;

                      return (
                        <TableRow
                          key={item.id}
                          ref={(node) =>
                            registerRowRef(`desktop:${item.id}`, node)
                          }
                          tabIndex={0}
                          role="button"
                          onClick={() => onSelectPayment(item)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              onSelectPayment(item);
                            }
                          }}
                          className={cn(
                            "cursor-pointer focus-visible:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
                            isHighlighted &&
                              "bg-[var(--brand-subtle)] hover:bg-[var(--brand-subtle)]"
                          )}
                        >
                          <TableCell className="pl-4 whitespace-normal">
                            <div className="flex flex-wrap items-center gap-1.5">
                              <span className="font-medium text-foreground break-words">
                                {item.request.recipient_name}
                              </span>
                              {isHighlighted && (
                                <span className="ui-tag">
                                  {t.queue.newBadge}
                                </span>
                              )}
                            </div>
                            <div className="mt-0.5 font-mono text-xs tabular-nums text-muted-foreground">
                              <span>
                                {interpolate(t.common.binPrefix, {
                                  bin: item.request.recipient_bin,
                                })}
                              </span>
                              <span> · </span>
                              <span className="break-all">
                                {item.request.recipient_iik}
                              </span>
                            </div>
                          </TableCell>
                          <TableCell className="text-right font-medium tabular-nums whitespace-nowrap text-foreground">
                            {formatMoney(item.request.amount_kzt)}
                          </TableCell>
                          <TableCell className="max-w-[220px] lg:max-w-sm whitespace-normal text-[var(--text-secondary)]">
                            <span className="line-clamp-2 break-words">
                              {item.request.purpose}
                            </span>
                          </TableCell>
                          <TableCell className="whitespace-normal">
                            <div className="flex min-w-0 flex-col items-start gap-1">
                              <VerdictBadge
                                verdict={item.result.verdict}
                                label={
                                  item.result.verdict === "green" &&
                                  item.result.signals.some(
                                    (s) => s.rule_id === "budget_payment"
                                  )
                                    ? t.signalRules.budget_payment
                                    : undefined
                                }
                              />
                              {primaryReason && (
                                <p
                                  title={primaryReason}
                                  className="max-w-[240px] lg:max-w-[300px] truncate text-xs leading-4 text-[var(--text-secondary)]"
                                >
                                  {primaryReason}
                                </p>
                              )}
                              {approval && approvalStyle && approvalLabel && (
                                <span
                                  className={cn(
                                    "ui-status",
                                    approvalStyle.badgeClass
                                  )}
                                >
                                  <span
                                    aria-hidden="true"
                                    className={cn(
                                      "ui-status-dot",
                                      APPROVAL_DOT_CLASS[approval.status]
                                    )}
                                  />
                                  <span>{approvalLabel}</span>
                                </span>
                              )}
                              {directorComment && (
                                <p className="max-w-[220px] line-clamp-2 text-xs text-muted-foreground break-words">
                                  {interpolate(t.queue.directorPrefix, {
                                    comment: directorComment,
                                  })}
                                </p>
                              )}
                            </div>
                          </TableCell>
                          <TableCell className="pr-3 text-right text-muted-foreground">
                            <ChevronRight className="ml-auto size-4" />
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <NewPaymentDialog
        key={prefillRequest ? JSON.stringify(prefillRequest) : "new-payment"}
        open={isDialogOpen}
        onOpenChange={handleDialogOpenChange}
        prefillRequest={prefillRequest}
        onPaymentCreated={handlePaymentCreated}
        onOpenPaymentCheck={(id, request, result) => {
          if (onSelectPaymentById) {
            onSelectPaymentById(id);
          } else {
            onSelectPayment({ id, request, result });
          }
        }}
        onNetworkError={onNetworkError}
      />
    </div>
  );
}
