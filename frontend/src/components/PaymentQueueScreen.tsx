"use client";

import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowUpDown,
  ArrowUpRight,
  ChevronDown,
  ChevronRight,
  ClipboardCheck,
  FileText,
  Inbox,
  Plus,
  RefreshCw,
  Search,
  SearchX,
  Wallet,
  X,
} from "lucide-react";
import { NewPaymentDialog } from "@/components/NewPaymentDialog";
import { Badge } from "@/components/ui/badge";
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
import { VERDICT_STYLES } from "@/lib/format";
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

  const signableQueue = useMemo(
    () => queue.filter((item) => item.result.verdict !== "invalid"),
    [queue]
  );

  const attentionCount = useMemo(
    () => queue.filter((item) => needsAttention(item.result.verdict)).length,
    [queue]
  );

  const pendingApprovalsCount = useMemo(
    () => approvals.filter((item) => item.status === "pending").length,
    [approvals]
  );

  const totalSignableAmount = useMemo(
    () =>
      signableQueue.reduce(
        (sum, item) => sum + (item.request.amount_kzt || 0),
        0
      ),
    [signableQueue]
  );

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
    <div className="space-y-5 sm:space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold tracking-tight text-foreground sm:text-2xl">
            {t.queue.title}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {t.queue.description}
          </p>
        </div>

        <Tooltip>
          <TooltipTrigger
            render={
              <Button
                type="button"
                size="lg"
                onClick={() => setDialogOpen(true)}
                className="min-h-11 w-full gap-2 rounded-xl px-4 font-semibold shadow-[0_2px_8px_rgba(0,171,117,0.22)] sm:min-h-10 sm:w-auto"
              />
            }
          >
            <Plus className="size-4" />
            <span>{t.queue.addPaymentButton}</span>
            <kbd
              aria-hidden="true"
              className="ml-0.5 hidden rounded border border-white/30 bg-white/15 px-1.5 py-0.5 font-mono text-[10px] font-semibold leading-none text-white sm:inline-flex"
            >
              N
            </kbd>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            {t.queue.newPaymentTooltip}
          </TooltipContent>
        </Tooltip>
      </div>

      {/* Summary tiles: 2 columns on phone, 4 on desktop */}
      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        {isLoading && queue.length === 0 ? (
          Array.from({ length: 4 }).map((_, index) => (
            <Card key={`tile-skeleton-${index}`} className="py-4">
              <CardContent className="space-y-3">
                <div className="flex items-center justify-between gap-2">
                  <Skeleton className="h-3.5 w-24" />
                  <Skeleton className="size-8 rounded-xl" />
                </div>
                <Skeleton className="h-8 w-16" />
                <Skeleton className="h-3 w-28" />
              </CardContent>
            </Card>
          ))
        ) : (
          <>
            <button
              type="button"
              onClick={resetFilters}
              className="group text-left rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <Card className="h-full py-4 transition-colors group-hover:border-primary/40">
                <CardContent className="flex h-full flex-col justify-between gap-2.5">
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-xs font-medium text-muted-foreground sm:text-sm">
                      {t.queue.tiles.toSignLabel}
                    </span>
                    <div className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-accent text-[var(--brand-text)]">
                      <FileText className="size-4" />
                    </div>
                  </div>
                  <div className="text-2xl font-bold tabular-nums text-foreground sm:text-3xl">
                    {signableQueue.length}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {t.queue.tiles.toSignHint}
                  </div>
                </CardContent>
              </Card>
            </button>

            <Card className="h-full py-4">
              <CardContent className="flex h-full flex-col justify-between gap-2.5">
                <div className="flex items-start justify-between gap-2">
                  <span className="text-xs font-medium text-muted-foreground sm:text-sm">
                    {t.queue.tiles.needsAttentionLabel}
                  </span>
                  <div
                    className={cn(
                      "flex size-8 shrink-0 items-center justify-center rounded-xl",
                      attentionCount > 0
                        ? "bg-amber-50 text-amber-700"
                        : "bg-accent text-[var(--brand-text)]"
                    )}
                  >
                    <AlertTriangle className="size-4" />
                  </div>
                </div>
                <div
                  className={cn(
                    "text-2xl font-bold tabular-nums sm:text-3xl",
                    attentionCount > 0 ? "text-amber-700" : "text-foreground"
                  )}
                >
                  {attentionCount}
                </div>
                <div className="text-xs text-muted-foreground">
                  {attentionCount > 0
                    ? t.queue.tiles.needsAttentionHint
                    : t.queue.tiles.allClearHint}
                </div>
              </CardContent>
            </Card>

            <Link
              href="/approvals"
              className="group block rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <Card className="h-full py-4 transition-colors group-hover:border-primary/40">
                <CardContent className="flex h-full flex-col justify-between gap-2.5">
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-xs font-medium text-muted-foreground sm:text-sm">
                      {t.queue.tiles.pendingApprovalsLabel}
                    </span>
                    <div
                      className={cn(
                        "flex size-8 shrink-0 items-center justify-center rounded-xl",
                        approvalsError
                          ? "bg-muted text-muted-foreground"
                          : pendingApprovalsCount > 0
                            ? "bg-amber-50 text-amber-700"
                            : "bg-accent text-[var(--brand-text)]"
                      )}
                    >
                      <ClipboardCheck className="size-4" />
                    </div>
                  </div>
                  <div className="text-2xl font-bold tabular-nums text-foreground sm:text-3xl">
                    {approvalsError ? "—" : pendingApprovalsCount}
                  </div>
                  <div className="flex items-center gap-1 text-xs font-medium text-[var(--brand-text)]">
                    <span>
                      {approvalsError
                        ? t.queue.tiles.pendingApprovalsUnavailable
                        : t.queue.tiles.pendingApprovalsHint}
                    </span>
                    {!approvalsError && (
                      <ArrowUpRight className="size-3.5 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
                    )}
                  </div>
                </CardContent>
              </Card>
            </Link>

            <Card className="h-full py-4">
              <CardContent className="flex h-full flex-col justify-between gap-2.5">
                <div className="flex items-start justify-between gap-2">
                  <span className="text-xs font-medium text-muted-foreground sm:text-sm">
                    {t.queue.tiles.totalAmountLabel}
                  </span>
                  <div className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-muted text-foreground/75">
                    <Wallet className="size-4" />
                  </div>
                </div>
                <div className="truncate whitespace-nowrap text-lg font-bold tabular-nums text-foreground sm:text-2xl">
                  {formatMoney(totalSignableAmount)}
                </div>
                <div className="text-xs text-muted-foreground">
                  {t.queue.tiles.totalAmountHint}
                </div>
              </CardContent>
            </Card>
          </>
        )}
      </div>

      {/* Main Queue Card */}
      <Card className="min-w-0 py-0">
        {/* Toolbar: Search + Verdict Chips */}
        <div className="border-b border-border p-4 space-y-3 sm:px-5">
          {isLoading && queue.length === 0 ? (
            <div className="space-y-3">
              <Skeleton className="h-10 w-full max-w-md rounded-xl" />
              <div className="flex flex-wrap gap-2">
                <Skeleton className="h-8 w-20 rounded-full" />
                <Skeleton className="h-8 w-32 rounded-full" />
                <Skeleton className="h-8 w-32 rounded-full" />
                <Skeleton className="h-8 w-36 rounded-full" />
              </div>
            </div>
          ) : (
            <>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
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
                    className="h-11 rounded-xl bg-background/70 pl-9 pr-10 sm:h-10 [&::-webkit-search-cancel-button]:hidden"
                  />
                  {searchQuery ? (
                    <button
                      type="button"
                      onClick={() => {
                        setSearchQuery("");
                        searchInputRef.current?.focus();
                      }}
                      aria-label={t.queue.clearSearch}
                      className="absolute top-1/2 right-1.5 flex size-8 -translate-y-1/2 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      <X className="size-4" />
                    </button>
                  ) : (
                    <Tooltip>
                      <TooltipTrigger
                        render={
                          <kbd
                            aria-hidden="true"
                            className="absolute top-1/2 right-2.5 hidden -translate-y-1/2 cursor-default items-center justify-center rounded-md border border-border bg-card px-1.5 py-0.5 font-mono text-[11px] font-medium text-muted-foreground sm:inline-flex"
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
                    <ArrowUpDown
                      aria-hidden="true"
                      className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground"
                    />
                    <select
                      aria-label={t.queue.sortLabel}
                      value={sortOrder}
                      onChange={(e) =>
                        setSortOrder(e.target.value as QueueSort)
                      }
                      className="h-10 w-full appearance-none rounded-xl border border-input bg-background/70 pl-8 pr-8 text-xs font-medium text-foreground shadow-xs transition-colors hover:bg-muted/50 focus-visible:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 sm:h-9 sm:w-auto"
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
                    className={cn(
                      "inline-flex min-h-10 shrink-0 items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-all cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 sm:min-h-8",
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
                        className={cn(
                          "inline-flex min-h-10 shrink-0 items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-all cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 sm:min-h-8",
                          isSelected
                            ? cn(
                                style.badgeClass,
                                "ring-1 ring-current/25 font-semibold shadow-xs"
                              )
                            : "border-border bg-card text-foreground hover:bg-muted/70"
                        )}
                      >
                        <span
                          aria-hidden="true"
                          className={cn(
                            "size-2 shrink-0 rounded-full",
                            style.dotClass
                          )}
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
              {/* Phone skeleton cards */}
              <div className="flex flex-col gap-3 p-3 sm:p-4 md:hidden">
                {Array.from({ length: 4 }).map((_, index) => (
                  <div
                    key={`card-skeleton-${index}`}
                    className="rounded-xl border border-border bg-card p-3.5 space-y-3"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <Skeleton className="h-5 w-44" />
                      <Skeleton className="h-6 w-24 rounded-full" />
                    </div>
                    <Skeleton className="h-7 w-32" />
                    <Skeleton className="h-3.5 w-56" />
                    <Skeleton className="h-4 w-full" />
                  </div>
                ))}
              </div>

              {/* Desktop skeleton table */}
              <div className="hidden md:block">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-muted/40 hover:bg-muted/40">
                      <TableHead className="pl-4 lg:pl-5">
                        {t.queue.colRecipient}
                      </TableHead>
                      <TableHead className="text-right">
                        {t.queue.colAmount}
                      </TableHead>
                      <TableHead>{t.queue.colPurpose}</TableHead>
                      <TableHead className="whitespace-normal">
                        {t.queue.colCheckResult}
                      </TableHead>
                      <TableHead className="w-9 pr-3 lg:pr-4" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {Array.from({ length: 5 }).map((_, index) => (
                      <TableRow
                        key={`row-skeleton-${index}`}
                        className="hover:bg-transparent"
                      >
                        <TableCell className="pl-4 lg:pl-5 py-4">
                          <div className="space-y-2">
                            <Skeleton className="h-4 w-48" />
                            <Skeleton className="h-3 w-64" />
                          </div>
                        </TableCell>
                        <TableCell className="py-4">
                          <Skeleton className="ml-auto h-4 w-24" />
                        </TableCell>
                        <TableCell className="py-4">
                          <Skeleton className="h-4 w-44" />
                        </TableCell>
                        <TableCell className="py-4">
                          <Skeleton className="h-6 w-28 rounded-full" />
                        </TableCell>
                        <TableCell className="pr-3 lg:pr-4 py-4">
                          <Skeleton className="ml-auto size-4 rounded" />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </>
          ) : hasError && queue.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-3 py-14 px-6 text-center">
              <div className="flex size-11 items-center justify-center rounded-2xl bg-red-50 text-red-600">
                <AlertTriangle className="size-5" />
              </div>
              <p className="max-w-md text-sm text-muted-foreground">
                {t.queue.loadErrorEmpty}
              </p>
              <Button
                type="button"
                variant="outline"
                onClick={() => void onRefreshQueue()}
                className="min-h-11 gap-2 rounded-xl sm:min-h-9"
              >
                <RefreshCw className="size-4" />
                <span>{t.common.retry}</span>
              </Button>
            </div>
          ) : queue.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-3 py-16 px-4 text-center">
              <div className="flex size-12 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
                <Inbox className="size-6" />
              </div>
              <div className="space-y-1">
                <div className="text-base font-semibold text-foreground">
                  {t.queue.emptyTitle}
                </div>
                <p className="max-w-md text-sm text-muted-foreground">
                  {t.queue.emptyQueue}
                </p>
              </div>
              <Button
                type="button"
                onClick={() => setDialogOpen(true)}
                className="mt-1 min-h-11 gap-2 rounded-xl sm:min-h-9"
              >
                <Plus className="size-4" />
                <span>{t.queue.addPaymentButton}</span>
              </Button>
            </div>
          ) : filteredQueue.length === 0 ? (
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
            <>
              {/* Mobile payment cards (< md) */}
              <div className="flex flex-col gap-3 p-3 sm:p-4 md:hidden">
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
                  const isHighlighted = highlightedId === item.id;

                  return (
                    <button
                      key={item.id}
                      ref={(node) => registerRowRef(`mobile:${item.id}`, node)}
                      type="button"
                      onClick={() => onSelectPayment(item)}
                      className={cn(
                        "w-full min-h-11 rounded-xl border bg-card p-3.5 text-left shadow-xs transition-all hover:bg-muted/50 active:bg-muted/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
                        isHighlighted
                          ? "border-primary bg-accent/60 ring-2 ring-primary/35"
                          : "border-border"
                      )}
                    >
                      <div className="flex items-start justify-between gap-2.5">
                        <div className="min-w-0 flex-1 space-y-1">
                          <div className="flex flex-wrap items-center gap-1.5">
                            <span className="text-base font-semibold leading-snug text-foreground break-words">
                              {item.request.recipient_name}
                            </span>
                            {isHighlighted && (
                              <Badge
                                variant="outline"
                                className="h-auto border-primary/30 bg-accent px-1.5 py-0.5 text-[10px] font-semibold text-accent-foreground"
                              >
                                {t.queue.newBadge}
                              </Badge>
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

                      <div className="mt-2 flex items-center justify-between gap-2">
                        <div className="text-xl font-bold tabular-nums whitespace-nowrap text-foreground">
                          {formatMoney(item.request.amount_kzt)}
                        </div>
                        <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
                      </div>

                      <div className="mt-1.5 flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5 font-mono text-xs text-muted-foreground">
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

                      <p className="mt-2 line-clamp-2 text-sm text-muted-foreground break-words">
                        {item.request.purpose}
                      </p>

                      {(approvalStyle || directorComment) && (
                        <div className="mt-2.5 flex flex-col items-start gap-1.5 border-t border-border/60 pt-2.5">
                          {approvalStyle && approvalLabel && (
                            <Badge
                              variant="outline"
                              className={cn(
                                "h-auto px-2 py-0.5 text-[11px] font-medium",
                                approvalStyle.badgeClass
                              )}
                            >
                              {approvalLabel}
                            </Badge>
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
                    <TableRow className="bg-muted/40 hover:bg-muted/40">
                      <TableHead className="pl-4 lg:pl-5">
                        {t.queue.colRecipient}
                      </TableHead>
                      <TableHead className="text-right">
                        {t.queue.colAmount}
                      </TableHead>
                      <TableHead>{t.queue.colPurpose}</TableHead>
                      <TableHead className="whitespace-normal">
                        {t.queue.colCheckResult}
                      </TableHead>
                      <TableHead className="w-9 pr-3 lg:pr-4" />
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
                            "cursor-pointer transition-colors hover:bg-muted/60 focus-visible:bg-accent/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
                            isHighlighted && "bg-accent/65 hover:bg-accent/80"
                          )}
                        >
                          <TableCell className="pl-4 lg:pl-5 py-3.5 whitespace-normal">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="font-medium text-foreground break-words">
                                {item.request.recipient_name}
                              </span>
                              {isHighlighted && (
                                <Badge
                                  variant="outline"
                                  className="h-auto border-primary/30 bg-card px-1.5 py-0.5 text-[10px] font-semibold text-accent-foreground"
                                >
                                  {t.queue.newBadge}
                                </Badge>
                              )}
                            </div>
                            <div className="mt-0.5 font-mono text-xs text-muted-foreground">
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
                          <TableCell className="py-3.5 text-right font-semibold tabular-nums whitespace-nowrap text-foreground">
                            {formatMoney(item.request.amount_kzt)}
                          </TableCell>
                          <TableCell className="py-3.5 max-w-[220px] lg:max-w-sm whitespace-normal text-muted-foreground">
                            <span className="line-clamp-2 break-words">
                              {item.request.purpose}
                            </span>
                          </TableCell>
                          <TableCell className="py-3.5 whitespace-normal">
                            <div className="flex flex-col items-start gap-1.5">
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
                              {approvalStyle && approvalLabel && (
                                <Badge
                                  variant="outline"
                                  className={cn(
                                    "h-auto px-2 py-0.5 text-[11px] font-medium",
                                    approvalStyle.badgeClass
                                  )}
                                >
                                  {approvalLabel}
                                </Badge>
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
                          <TableCell className="pr-3 lg:pr-4 py-3.5 text-right text-muted-foreground">
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
