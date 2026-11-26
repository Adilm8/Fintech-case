"use client";

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import Link from "next/link";
import { Loader2, Search, X } from "lucide-react";
import { useAppData } from "@/components/AppShell";
import { VerdictBadge } from "@/components/VerdictBadge";
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
import { useT } from "@/i18n";
import { getAuditLog } from "@/lib/api";
import {
  buildCheckHistoryCsv,
  downloadCsvFile,
  getServerSessionChecksSnapshot,
  getSessionChecksSnapshot,
  mergeCheckHistory,
  subscribeSessionChecks,
  type MergedCheckHistoryRow,
} from "@/lib/check-history";
import { VERDICT_STYLES } from "@/lib/format";
import { getPaymentCheckHref } from "@/lib/queue-storage";
import { notify } from "@/lib/toast";
import type { AuditEntry, Verdict } from "@/lib/types";
import { formatIikGrouped } from "@/lib/validators";
import { cn } from "cn";

const VERDICT_ORDER: readonly Verdict[] = [
  "green",
  "yellow",
  "red",
  "grey",
  "invalid",
] as const;

type VerdictFilter = "all" | Verdict;

function isEditableElement(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") {
    return true;
  }
  return target.isContentEditable;
}

function formatDateTime(
  iso: string,
  formatDate: (dateStr: string | null | undefined) => string
): string {
  if (!iso) return "—";
  const datePart = formatDate(iso);
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) {
    return datePart;
  }
  const hh = String(parsed.getHours()).padStart(2, "0");
  const mm = String(parsed.getMinutes()).padStart(2, "0");
  const ss = String(parsed.getSeconds()).padStart(2, "0");
  return `${datePart}, ${hh}:${mm}:${ss}`;
}

export default function CheckHistoryPage() {
  const { queue, approvals, resetCounter } = useAppData();
  const { t, lang, mounted, formatMoney, formatDate, interpolate } = useT();

  const storedSessionChecks = useSyncExternalStore(
    subscribeSessionChecks,
    getSessionChecksSnapshot,
    getServerSessionChecksSnapshot
  );
  const sessionChecks = mounted
    ? storedSessionChecks
    : getServerSessionChecksSnapshot();

  const [auditEntries, setAuditEntries] = useState<AuditEntry[]>([]);
  const [isLoadingAudit, setIsLoadingAudit] = useState(true);
  const [auditError, setAuditError] = useState(false);
  const [refreshNonce, setRefreshNonce] = useState(0);

  const [searchQuery, setSearchQuery] = useState("");
  const [verdictFilter, setVerdictFilter] = useState<VerdictFilter>("all");

  const searchInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!mounted) return;
    const controller = new AbortController();
    let active = true;

    const load = async () => {
      setIsLoadingAudit(true);
      try {
        const entries = await getAuditLog(100, lang, {
          signal: controller.signal,
        });
        if (!active) return;
        setAuditEntries(entries);
        setAuditError(false);
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") return;
        if (!active) return;
        setAuditError(true);
      } finally {
        if (active) {
          setIsLoadingAudit(false);
        }
      }
    };

    void load();
    return () => {
      active = false;
      controller.abort();
    };
  }, [lang, mounted, refreshNonce, resetCounter]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      if (isEditableElement(event.target)) return;
      if (document.querySelector('[data-slot="dialog-content"]')) return;
      if (event.key === "/") {
        event.preventDefault();
        searchInputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const mergedRows = useMemo(
    () => mergeCheckHistory(sessionChecks, auditEntries, queue, approvals),
    [sessionChecks, auditEntries, queue, approvals]
  );

  const signalRulesMap: Record<string, string> = t.signalRules;
  const actionLabelsMap: Record<string, string> = t.history.actions;

  const resolveSignalLabel = (ruleId: string): string =>
    signalRulesMap[ruleId] ?? ruleId;

  const resolveActionLabel = (action: string): string =>
    actionLabelsMap[action] ?? action;

  const resolveSourceLabel = (
    source: MergedCheckHistoryRow["source"]
  ): string => {
    if (source === "both") return t.history.sourceBoth;
    if (source === "session") return t.history.sourceSession;
    return t.history.sourceAudit;
  };

  const verdictCounts = useMemo(() => {
    const counts: Record<Verdict, number> = {
      green: 0,
      yellow: 0,
      red: 0,
      grey: 0,
      invalid: 0,
    };
    for (const row of mergedRows) {
      if (row.verdict in counts) {
        counts[row.verdict] += 1;
      }
    }
    return counts;
  }, [mergedRows]);

  const availableVerdicts = useMemo(
    () =>
      VERDICT_ORDER.filter(
        (verdict) => verdictCounts[verdict] > 0 || verdictFilter === verdict
      ),
    [verdictCounts, verdictFilter]
  );

  const filteredRows = useMemo(() => {
    const trimmed = searchQuery.trim().toLowerCase();
    const compact = trimmed.replace(/\s+/g, "");

    return mergedRows.filter((row) => {
      if (verdictFilter !== "all" && row.verdict !== verdictFilter) {
        return false;
      }
      if (!trimmed) return true;

      const name = (row.recipient_name ?? "").toLowerCase();
      const bin = (row.recipient_bin ?? "").replace(/\s+/g, "").toLowerCase();
      const iik = (row.recipient_iik ?? "").replace(/\s+/g, "").toLowerCase();
      const checkId = row.check_id.toLowerCase();
      const hash = (row.request_sha256 ?? "").toLowerCase();
      const signalsMatch = row.signal_ids.some(
        (id) =>
          id.toLowerCase().includes(trimmed) ||
          (signalRulesMap[id] ?? "").toLowerCase().includes(trimmed)
      );
      const actionsMatch = row.actions.some(
        (act) =>
          act.toLowerCase().includes(trimmed) ||
          (actionLabelsMap[act] ?? "").toLowerCase().includes(trimmed)
      );

      return (
        name.includes(trimmed) ||
        bin.includes(compact) ||
        iik.includes(compact) ||
        checkId.includes(compact) ||
        hash.includes(compact) ||
        signalsMatch ||
        actionsMatch
      );
    });
  }, [mergedRows, verdictFilter, searchQuery, signalRulesMap, actionLabelsMap]);

  const hasActiveFilters =
    searchQuery.trim().length > 0 || verdictFilter !== "all";

  const resetFilters = () => {
    setSearchQuery("");
    setVerdictFilter("all");
  };

  const handleExportCsv = () => {
    if (filteredRows.length === 0) return;
    const csv = buildCheckHistoryCsv(
      filteredRows,
      resolveActionLabel,
      (verdict) => t.verdicts[verdict] ?? verdict,
      resolveSignalLabel
    );
    const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
    downloadCsvFile(csv, `business-shield-checks-${stamp}.csv`);
    notify.success(
      t.toast.csvExportedTitle,
      interpolate(t.toast.csvExportedDescription, {
        count: filteredRows.length,
      })
    );
  };

  const highRiskCount = verdictCounts.red + verdictCounts.invalid;
  const reviewCount = verdictCounts.yellow + verdictCounts.grey;
  const cleanCount = verdictCounts.green;

  const showInitialSkeleton =
    !mounted || (isLoadingAudit && mergedRows.length === 0);

  return (
    <div className="space-y-4 sm:space-y-5">
      {/* Header */}
      <div className="ui-page-header">
        <div className="min-w-0">
          <h1 className="ui-page-title">{t.history.title}</h1>
          <p className="ui-page-subtitle">{t.history.subtitle}</p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={() => setRefreshNonce((n) => n + 1)}
            disabled={isLoadingAudit}
            className="min-h-10 flex-1 sm:min-h-9 sm:flex-initial"
          >
            {isLoadingAudit && (
              <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
            )}
            <span>{t.common.refresh}</span>
          </Button>

          <Button
            type="button"
            onClick={handleExportCsv}
            disabled={filteredRows.length === 0}
            className="min-h-10 flex-1 sm:min-h-9 sm:flex-initial"
          >
            {t.history.exportCsv}
          </Button>
        </div>
      </div>

      {auditError && (
        <div
          role="alert"
          className="ui-notice ui-notice-warn flex flex-wrap items-center justify-between gap-2 text-xs text-foreground"
        >
          <span>{t.history.loadErrorNotice}</span>
          <Button
            type="button"
            variant="outline"
            size="xs"
            onClick={() => setRefreshNonce((n) => n + 1)}
          >
            {t.common.retry}
          </Button>
        </div>
      )}

      {/* Summary strip */}
      <div className="ui-kpi-strip">
        {showInitialSkeleton ? (
          Array.from({ length: 4 }).map((_, idx) => (
            <div key={`hist-tile-skel-${idx}`} className="ui-kpi-cell">
              <Skeleton className="h-3.5 w-24 rounded-[4px]" />
              <Skeleton className="h-6 w-16 rounded-[4px]" />
            </div>
          ))
        ) : (
          <>
            <div className="ui-kpi-cell">
              <span className="ui-kpi-label">{t.history.tiles.total}</span>
              <div className="ui-kpi-value">{mergedRows.length}</div>
            </div>

            <div className="ui-kpi-cell">
              <span className="ui-kpi-label">{t.history.tiles.highRisk}</span>
              <div
                className={cn(
                  "ui-kpi-value",
                  highRiskCount > 0 && "text-[var(--status-danger-text)]"
                )}
              >
                {highRiskCount}
              </div>
            </div>

            <div className="ui-kpi-cell">
              <span className="ui-kpi-label">{t.history.tiles.review}</span>
              <div
                className={cn(
                  "ui-kpi-value",
                  reviewCount > 0 && "text-[var(--status-warn-text)]"
                )}
              >
                {reviewCount}
              </div>
            </div>

            <div className="ui-kpi-cell">
              <span className="ui-kpi-label">{t.history.tiles.clean}</span>
              <div className="ui-kpi-value">{cleanCount}</div>
            </div>
          </>
        )}
      </div>

      {/* Main History Panel */}
      <Card className="min-w-0 py-0">
        <div className="space-y-3 border-b border-border p-4">
          {showInitialSkeleton ? (
            <div className="space-y-3">
              <Skeleton className="h-9 w-full max-w-md rounded-[6px]" />
              <div className="flex flex-wrap gap-1.5">
                <Skeleton className="h-8 w-20 rounded-[6px]" />
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
                    placeholder={t.history.searchPlaceholder}
                    aria-label={t.history.searchAriaLabel}
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

                <div className="text-xs font-medium text-muted-foreground tabular-nums">
                  {hasActiveFilters
                    ? interpolate(t.history.shownOfTotal, {
                        shown: filteredRows.length,
                        total: mergedRows.length,
                      })
                    : interpolate(t.history.totalChecks, {
                        count: mergedRows.length,
                      })}
                </div>
              </div>

              {mergedRows.length > 0 && (
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
                      {mergedRows.length}
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
          {showInitialSkeleton ? (
            <>
              <div className="divide-y divide-border md:hidden">
                {Array.from({ length: 4 }).map((_, idx) => (
                  <div
                    key={`hist-card-skel-${idx}`}
                    className="space-y-2 p-4"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <Skeleton className="h-4 w-36 rounded-[4px]" />
                      <Skeleton className="h-4 w-24 rounded-[4px]" />
                    </div>
                    <Skeleton className="h-4 w-52 rounded-[4px]" />
                    <Skeleton className="h-3.5 w-full rounded-[4px]" />
                  </div>
                ))}
              </div>
              <div className="hidden md:block">
                <Table>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent">
                      <TableHead className="pl-4">
                        {t.history.colTime}
                      </TableHead>
                      <TableHead>{t.history.colCheck}</TableHead>
                      <TableHead>{t.history.colVerdict}</TableHead>
                      <TableHead>{t.history.colSignals}</TableHead>
                      <TableHead className="pr-4">
                        {t.history.colAction}
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {Array.from({ length: 5 }).map((_, idx) => (
                      <TableRow key={`hist-row-skel-${idx}`}>
                        <TableCell className="pl-4 py-3">
                          <Skeleton className="h-4 w-28 rounded-[4px]" />
                        </TableCell>
                        <TableCell className="py-3">
                          <div className="space-y-1.5">
                            <Skeleton className="h-4 w-44 rounded-[4px]" />
                            <Skeleton className="h-3 w-32 rounded-[4px]" />
                          </div>
                        </TableCell>
                        <TableCell className="py-3">
                          <Skeleton className="h-4 w-28 rounded-[4px]" />
                        </TableCell>
                        <TableCell className="py-3">
                          <Skeleton className="h-4 w-48 rounded-[4px]" />
                        </TableCell>
                        <TableCell className="pr-4 py-3">
                          <Skeleton className="h-4 w-24 rounded-[4px]" />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </>
          ) : mergedRows.length === 0 ? (
            <div className="ui-empty">
              <div className="ui-empty-title">{t.history.emptyTitle}</div>
              <p className="ui-empty-desc">{t.history.emptyDescription}</p>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <Link
                  href="/?new=1"
                  className="inline-flex min-h-10 items-center rounded-[6px] bg-primary px-3 text-xs font-medium text-primary-foreground transition-colors hover:bg-[var(--brand-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:min-h-8"
                >
                  {t.history.emptyActionNew}
                </Link>
                <Link
                  href="/"
                  className="inline-flex min-h-10 items-center rounded-[6px] border border-input bg-card px-3 text-xs font-medium text-foreground transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:min-h-8"
                >
                  {t.history.emptyActionQueue}
                </Link>
              </div>
            </div>
          ) : filteredRows.length === 0 ? (
            <div className="ui-empty">
              <div className="ui-empty-title">
                {t.history.emptyFilteredTitle}
              </div>
              <p className="ui-empty-desc">
                {t.history.emptyFilteredDescription}
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
                {filteredRows.map((row) => (
                  <div key={row.check_id} className="space-y-2 px-4 py-3">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 space-y-0.5">
                        <div className="text-xs text-muted-foreground tabular-nums">
                          {formatDateTime(row.timestamp, formatDate)}
                        </div>
                        <div className="font-mono text-xs font-medium tabular-nums text-foreground break-all">
                          {row.check_id}
                        </div>
                      </div>
                      <VerdictBadge verdict={row.verdict} className="shrink-0" />
                    </div>

                    {row.recipient_name ? (
                      <div className="space-y-0.5">
                        <div className="flex flex-wrap items-baseline justify-between gap-2">
                          <span className="text-sm font-medium text-foreground break-words">
                            {row.recipient_name}
                          </span>
                          {row.amount_kzt !== null && (
                            <span className="text-sm font-semibold tabular-nums whitespace-nowrap text-foreground">
                              {formatMoney(row.amount_kzt)}
                            </span>
                          )}
                        </div>
                        {(row.recipient_bin || row.recipient_iik) && (
                          <div className="flex flex-wrap items-baseline gap-x-1.5 font-mono text-xs tabular-nums text-muted-foreground">
                            {row.recipient_bin && (
                              <span>
                                {interpolate(t.common.binPrefix, {
                                  bin: row.recipient_bin,
                                })}
                              </span>
                            )}
                            {row.recipient_bin && row.recipient_iik && (
                              <span aria-hidden="true">·</span>
                            )}
                            {row.recipient_iik && (
                              <span className="break-all">
                                {formatIikGrouped(row.recipient_iik)}
                              </span>
                            )}
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="space-y-0.5 text-xs text-muted-foreground">
                        <div>{t.history.auditOnlyLabel}</div>
                        {row.request_sha256 && (
                          <div className="font-mono text-[11px] tabular-nums">
                            {interpolate(t.history.hashShort, {
                              hash: `${row.request_sha256.slice(0, 12)}…`,
                            })}
                          </div>
                        )}
                      </div>
                    )}

                    <div className="flex flex-wrap items-center gap-1">
                      {row.signal_ids.length === 0 ? (
                        <span className="text-xs text-muted-foreground">
                          {t.history.noSignals}
                        </span>
                      ) : (
                        row.signal_ids.map((sigId) => (
                          <span
                            key={sigId}
                            className="ui-tag max-w-full whitespace-normal"
                          >
                            {resolveSignalLabel(sigId)}
                          </span>
                        ))
                      )}
                    </div>

                    <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-2 text-xs">
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                        {row.actions.length > 0 && (
                          <span className="font-medium text-foreground">
                            {row.actions.map(resolveActionLabel).join(" · ")}
                          </span>
                        )}
                        <span className="text-muted-foreground">
                          {resolveSourceLabel(row.source)}
                        </span>
                      </div>

                      {row.queue_item_id && (
                        <Link
                          href={getPaymentCheckHref(row.queue_item_id)}
                          className="font-medium text-[var(--brand-text)] hover:underline"
                        >
                          {t.history.openPayment}
                        </Link>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              {/* Desktop Table (>= md) */}
              <div className="hidden md:block">
                <Table>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent">
                      <TableHead className="w-[160px] pl-4">
                        {t.history.colTime}
                      </TableHead>
                      <TableHead>{t.history.colCheck}</TableHead>
                      <TableHead className="w-[170px]">
                        {t.history.colVerdict}
                      </TableHead>
                      <TableHead>{t.history.colSignals}</TableHead>
                      <TableHead className="w-[180px] pr-4">
                        {t.history.colAction}
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredRows.map((row) => (
                      <TableRow key={row.check_id} className="align-top">
                        <TableCell className="pl-4 text-xs text-muted-foreground tabular-nums whitespace-nowrap">
                          <div>{formatDateTime(row.timestamp, formatDate)}</div>
                          <div className="mt-0.5 font-mono text-[11px] text-[var(--text-secondary)]">
                            {row.check_id}
                          </div>
                        </TableCell>

                        <TableCell className="whitespace-normal">
                          {row.recipient_name ? (
                            <div className="space-y-0.5">
                              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                                <span className="font-medium text-foreground break-words">
                                  {row.recipient_name}
                                </span>
                                {row.amount_kzt !== null && (
                                  <span className="text-xs font-medium tabular-nums whitespace-nowrap text-foreground">
                                    {formatMoney(row.amount_kzt)}
                                  </span>
                                )}
                              </div>
                              {(row.recipient_bin || row.recipient_iik) && (
                                <div className="font-mono text-xs tabular-nums text-muted-foreground">
                                  {row.recipient_bin && (
                                    <span>
                                      {interpolate(t.common.binPrefix, {
                                        bin: row.recipient_bin,
                                      })}
                                    </span>
                                  )}
                                  {row.recipient_bin && row.recipient_iik && (
                                    <span> · </span>
                                  )}
                                  {row.recipient_iik && (
                                    <span className="break-all">
                                      {formatIikGrouped(row.recipient_iik)}
                                    </span>
                                  )}
                                </div>
                              )}
                            </div>
                          ) : (
                            <div className="space-y-0.5">
                              <div className="text-xs text-muted-foreground">
                                {t.history.auditOnlyLabel}
                              </div>
                              {row.request_sha256 && (
                                <div className="font-mono text-[11px] tabular-nums text-muted-foreground">
                                  {interpolate(t.history.hashShort, {
                                    hash: `${row.request_sha256.slice(0, 14)}…`,
                                  })}
                                </div>
                              )}
                            </div>
                          )}
                        </TableCell>

                        <TableCell className="whitespace-normal">
                          <div className="flex flex-col items-start gap-0.5">
                            <VerdictBadge verdict={row.verdict} />
                            {row.score !== null && (
                              <span className="font-mono text-[11px] text-muted-foreground tabular-nums">
                                {interpolate(t.history.scoreShort, {
                                  score: row.score,
                                })}
                              </span>
                            )}
                          </div>
                        </TableCell>

                        <TableCell className="whitespace-normal">
                          {row.signal_ids.length === 0 ? (
                            <span className="text-xs text-muted-foreground">
                              {t.history.noSignals}
                            </span>
                          ) : (
                            <div className="flex flex-wrap gap-1">
                              {row.signal_ids.map((sigId) => (
                                <span
                                  key={sigId}
                                  className="ui-tag max-w-full whitespace-normal"
                                >
                                  {resolveSignalLabel(sigId)}
                                </span>
                              ))}
                            </div>
                          )}
                        </TableCell>

                        <TableCell className="pr-4 whitespace-normal">
                          <div className="flex flex-col items-start gap-1 text-xs">
                            {row.actions.length > 0 && (
                              <span className="font-medium text-foreground">
                                {row.actions
                                  .map(resolveActionLabel)
                                  .join(" · ")}
                              </span>
                            )}
                            <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                              <span className="text-muted-foreground">
                                {resolveSourceLabel(row.source)}
                              </span>
                              {row.queue_item_id && (
                                <Link
                                  href={getPaymentCheckHref(row.queue_item_id)}
                                  className="font-medium text-[var(--brand-text)] hover:underline"
                                >
                                  {t.history.openPayment}
                                </Link>
                              )}
                            </div>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
