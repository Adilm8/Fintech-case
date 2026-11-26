"use client";

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  Download,
  History,
  Inbox,
  OctagonX,
  Plus,
  RefreshCw,
  Search,
  SearchX,
  ShieldAlert,
  X,
} from "lucide-react";
import { useAppData } from "@/components/AppShell";
import { VerdictBadge } from "@/components/VerdictBadge";
import { Alert, AlertDescription } from "@/components/ui/alert";
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
    <div className="space-y-5 sm:space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2.5">
            <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-accent text-[var(--brand-text)]">
              <History className="size-5" />
            </div>
            <h1 className="text-xl font-semibold tracking-tight text-foreground sm:text-2xl">
              {t.history.title}
            </h1>
          </div>
          <p className="mt-1.5 text-sm text-muted-foreground">
            {t.history.subtitle}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setRefreshNonce((n) => n + 1)}
            disabled={isLoadingAudit}
            className="min-h-11 flex-1 gap-1.5 rounded-xl sm:min-h-9 sm:flex-initial"
          >
            <RefreshCw
              className={cn("size-3.5", isLoadingAudit && "animate-spin")}
            />
            <span>{t.common.refresh}</span>
          </Button>

          <Button
            type="button"
            size="sm"
            onClick={handleExportCsv}
            disabled={filteredRows.length === 0}
            className="min-h-11 flex-1 gap-1.5 rounded-xl sm:min-h-9 sm:flex-initial"
          >
            <Download className="size-3.5" />
            <span>{t.history.exportCsv}</span>
          </Button>
        </div>
      </div>

      {auditError && (
        <Alert className="rounded-xl border-amber-300 bg-amber-50/90 text-amber-950">
          <AlertTriangle className="size-4 text-amber-700" />
          <AlertDescription className="flex flex-wrap items-center justify-between gap-2 text-amber-950">
            <span>{t.history.loadErrorNotice}</span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setRefreshNonce((n) => n + 1)}
              className="h-8 gap-1.5 border-amber-400 bg-card text-xs text-amber-950 hover:bg-amber-100"
            >
              <RefreshCw className="size-3.5" />
              <span>{t.common.retry}</span>
            </Button>
          </AlertDescription>
        </Alert>
      )}

      {/* Summary tiles */}
      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        {showInitialSkeleton ? (
          Array.from({ length: 4 }).map((_, idx) => (
            <Card key={`hist-tile-skel-${idx}`} className="py-4">
              <CardContent className="space-y-3">
                <div className="flex items-center justify-between gap-2">
                  <Skeleton className="h-3.5 w-24" />
                  <Skeleton className="size-8 rounded-xl" />
                </div>
                <Skeleton className="h-8 w-16" />
              </CardContent>
            </Card>
          ))
        ) : (
          <>
            <Card className="py-4">
              <CardContent className="flex flex-col justify-between gap-2">
                <div className="flex items-start justify-between gap-2">
                  <span className="text-xs font-medium text-muted-foreground sm:text-sm">
                    {t.history.tiles.total}
                  </span>
                  <div className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-muted text-foreground/75">
                    <History className="size-4" />
                  </div>
                </div>
                <div className="text-2xl font-bold tabular-nums text-foreground sm:text-3xl">
                  {mergedRows.length}
                </div>
              </CardContent>
            </Card>

            <Card className="py-4">
              <CardContent className="flex flex-col justify-between gap-2">
                <div className="flex items-start justify-between gap-2">
                  <span className="text-xs font-medium text-muted-foreground sm:text-sm">
                    {t.history.tiles.highRisk}
                  </span>
                  <div
                    className={cn(
                      "flex size-8 shrink-0 items-center justify-center rounded-xl",
                      highRiskCount > 0
                        ? "bg-red-50 text-red-600"
                        : "bg-muted text-muted-foreground"
                    )}
                  >
                    <OctagonX className="size-4" />
                  </div>
                </div>
                <div
                  className={cn(
                    "text-2xl font-bold tabular-nums sm:text-3xl",
                    highRiskCount > 0 ? "text-red-700" : "text-foreground"
                  )}
                >
                  {highRiskCount}
                </div>
              </CardContent>
            </Card>

            <Card className="py-4">
              <CardContent className="flex flex-col justify-between gap-2">
                <div className="flex items-start justify-between gap-2">
                  <span className="text-xs font-medium text-muted-foreground sm:text-sm">
                    {t.history.tiles.review}
                  </span>
                  <div
                    className={cn(
                      "flex size-8 shrink-0 items-center justify-center rounded-xl",
                      reviewCount > 0
                        ? "bg-amber-50 text-amber-700"
                        : "bg-muted text-muted-foreground"
                    )}
                  >
                    <ShieldAlert className="size-4" />
                  </div>
                </div>
                <div
                  className={cn(
                    "text-2xl font-bold tabular-nums sm:text-3xl",
                    reviewCount > 0 ? "text-amber-700" : "text-foreground"
                  )}
                >
                  {reviewCount}
                </div>
              </CardContent>
            </Card>

            <Card className="py-4">
              <CardContent className="flex flex-col justify-between gap-2">
                <div className="flex items-start justify-between gap-2">
                  <span className="text-xs font-medium text-muted-foreground sm:text-sm">
                    {t.history.tiles.clean}
                  </span>
                  <div className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-accent text-[var(--brand-text)]">
                    <CheckCircle2 className="size-4" />
                  </div>
                </div>
                <div className="text-2xl font-bold tabular-nums text-foreground sm:text-3xl">
                  {cleanCount}
                </div>
              </CardContent>
            </Card>
          </>
        )}
      </div>

      {/* Main History Card */}
      <Card className="min-w-0 py-0">
        <div className="border-b border-border p-4 space-y-3 sm:px-5">
          {showInitialSkeleton ? (
            <div className="space-y-3">
              <Skeleton className="h-10 w-full max-w-md rounded-xl" />
              <div className="flex flex-wrap gap-2">
                <Skeleton className="h-8 w-20 rounded-full" />
                <Skeleton className="h-8 w-28 rounded-full" />
                <Skeleton className="h-8 w-32 rounded-full" />
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
                    placeholder={t.history.searchPlaceholder}
                    aria-label={t.history.searchAriaLabel}
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
          {showInitialSkeleton ? (
            <>
              <div className="flex flex-col gap-3 p-3 sm:p-4 md:hidden">
                {Array.from({ length: 4 }).map((_, idx) => (
                  <div
                    key={`hist-card-skel-${idx}`}
                    className="space-y-3 rounded-xl border border-border bg-card p-3.5"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <Skeleton className="h-4 w-36" />
                      <Skeleton className="h-6 w-24 rounded-full" />
                    </div>
                    <Skeleton className="h-4 w-52" />
                    <Skeleton className="h-3.5 w-full" />
                  </div>
                ))}
              </div>
              <div className="hidden md:block">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-muted/40 hover:bg-muted/40">
                      <TableHead className="pl-4 lg:pl-5">
                        {t.history.colTime}
                      </TableHead>
                      <TableHead>{t.history.colCheck}</TableHead>
                      <TableHead>{t.history.colVerdict}</TableHead>
                      <TableHead>{t.history.colSignals}</TableHead>
                      <TableHead className="pr-4 lg:pr-5">
                        {t.history.colAction}
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {Array.from({ length: 5 }).map((_, idx) => (
                      <TableRow key={`hist-row-skel-${idx}`}>
                        <TableCell className="pl-4 lg:pl-5 py-4">
                          <Skeleton className="h-4 w-28" />
                        </TableCell>
                        <TableCell className="py-4">
                          <div className="space-y-1.5">
                            <Skeleton className="h-4 w-44" />
                            <Skeleton className="h-3 w-32" />
                          </div>
                        </TableCell>
                        <TableCell className="py-4">
                          <Skeleton className="h-6 w-28 rounded-full" />
                        </TableCell>
                        <TableCell className="py-4">
                          <Skeleton className="h-4 w-48" />
                        </TableCell>
                        <TableCell className="pr-4 lg:pr-5 py-4">
                          <Skeleton className="h-5 w-24" />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </>
          ) : mergedRows.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-3 py-16 px-4 text-center">
              <div className="flex size-12 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
                <Inbox className="size-6" />
              </div>
              <div className="space-y-1">
                <div className="text-base font-semibold text-foreground">
                  {t.history.emptyTitle}
                </div>
                <p className="max-w-md text-sm text-muted-foreground">
                  {t.history.emptyDescription}
                </p>
              </div>
              <div className="mt-1 flex flex-wrap items-center justify-center gap-2">
                <Link
                  href="/?new=1"
                  className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground shadow-xs transition-colors hover:bg-[var(--brand-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:min-h-9"
                >
                  <Plus className="size-4" />
                  <span>{t.history.emptyActionNew}</span>
                </Link>
                <Link
                  href="/"
                  className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-border bg-card px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:min-h-9"
                >
                  <span>{t.history.emptyActionQueue}</span>
                </Link>
              </div>
            </div>
          ) : filteredRows.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-3 py-14 px-4 text-center">
              <div className="flex size-12 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
                <SearchX className="size-6" />
              </div>
              <div className="space-y-1">
                <div className="text-base font-semibold text-foreground">
                  {t.history.emptyFilteredTitle}
                </div>
                <p className="max-w-md text-sm text-muted-foreground">
                  {t.history.emptyFilteredDescription}
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
              {/* Mobile Cards (< md) */}
              <div className="flex flex-col gap-3 p-3 sm:p-4 md:hidden">
                {filteredRows.map((row) => (
                  <div
                    key={row.check_id}
                    className="space-y-2.5 rounded-xl border border-border bg-card p-3.5 shadow-xs"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 space-y-0.5">
                        <div className="text-xs text-muted-foreground tabular-nums">
                          {formatDateTime(row.timestamp, formatDate)}
                        </div>
                        <div className="font-mono text-xs font-semibold text-foreground break-all">
                          {row.check_id}
                        </div>
                      </div>
                      <VerdictBadge verdict={row.verdict} className="shrink-0" />
                    </div>

                    {row.recipient_name ? (
                      <div className="space-y-1">
                        <div className="flex flex-wrap items-baseline justify-between gap-2">
                          <span className="text-sm font-semibold text-foreground break-words">
                            {row.recipient_name}
                          </span>
                          {row.amount_kzt !== null && (
                            <span className="text-sm font-bold tabular-nums whitespace-nowrap text-foreground">
                              {formatMoney(row.amount_kzt)}
                            </span>
                          )}
                        </div>
                        {(row.recipient_bin || row.recipient_iik) && (
                          <div className="flex flex-wrap items-baseline gap-x-1.5 font-mono text-xs text-muted-foreground">
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
                          <div className="font-mono text-[11px]">
                            {interpolate(t.history.hashShort, {
                              hash: `${row.request_sha256.slice(0, 12)}…`,
                            })}
                          </div>
                        )}
                      </div>
                    )}

                    <div className="flex flex-wrap items-center gap-1.5">
                      {row.signal_ids.length === 0 ? (
                        <span className="text-xs text-muted-foreground">
                          {t.history.noSignals}
                        </span>
                      ) : (
                        row.signal_ids.map((sigId) => (
                          <Badge
                            key={sigId}
                            variant="outline"
                            className="h-auto max-w-full whitespace-normal px-2 py-0.5 text-[11px] font-medium"
                          >
                            {resolveSignalLabel(sigId)}
                          </Badge>
                        ))
                      )}
                    </div>

                    <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border/70 pt-2">
                      <div className="flex flex-wrap items-center gap-1.5">
                        {row.actions.map((act) => (
                          <Badge
                            key={act}
                            variant="secondary"
                            className="h-auto px-2 py-0.5 text-[11px] font-medium"
                          >
                            {resolveActionLabel(act)}
                          </Badge>
                        ))}
                        <Badge
                          variant="outline"
                          className="h-auto px-2 py-0.5 text-[10px] font-medium text-muted-foreground"
                        >
                          {resolveSourceLabel(row.source)}
                        </Badge>
                      </div>

                      {row.queue_item_id && (
                        <Link
                          href={getPaymentCheckHref(row.queue_item_id)}
                          className="inline-flex items-center gap-1 text-xs font-semibold text-[var(--brand-text)] hover:underline"
                        >
                          <span>{t.history.openPayment}</span>
                          <ArrowUpRight className="size-3.5" />
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
                    <TableRow className="bg-muted/40 hover:bg-muted/40">
                      <TableHead className="w-[160px] pl-4 lg:pl-5">
                        {t.history.colTime}
                      </TableHead>
                      <TableHead>{t.history.colCheck}</TableHead>
                      <TableHead className="w-[170px]">
                        {t.history.colVerdict}
                      </TableHead>
                      <TableHead>{t.history.colSignals}</TableHead>
                      <TableHead className="w-[180px] pr-4 lg:pr-5">
                        {t.history.colAction}
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredRows.map((row) => (
                      <TableRow key={row.check_id} className="align-top">
                        <TableCell className="pl-4 lg:pl-5 py-3.5 text-xs text-muted-foreground tabular-nums whitespace-nowrap">
                          <div>{formatDateTime(row.timestamp, formatDate)}</div>
                          <div className="mt-1 font-mono text-[11px] text-foreground/80">
                            {row.check_id}
                          </div>
                        </TableCell>

                        <TableCell className="py-3.5 whitespace-normal">
                          {row.recipient_name ? (
                            <div className="space-y-0.5">
                              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                                <span className="font-medium text-foreground break-words">
                                  {row.recipient_name}
                                </span>
                                {row.amount_kzt !== null && (
                                  <span className="text-xs font-semibold tabular-nums whitespace-nowrap text-foreground">
                                    {formatMoney(row.amount_kzt)}
                                  </span>
                                )}
                              </div>
                              {(row.recipient_bin || row.recipient_iik) && (
                                <div className="font-mono text-xs text-muted-foreground">
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
                                <div className="font-mono text-[11px] text-muted-foreground">
                                  {interpolate(t.history.hashShort, {
                                    hash: `${row.request_sha256.slice(0, 14)}…`,
                                  })}
                                </div>
                              )}
                            </div>
                          )}
                        </TableCell>

                        <TableCell className="py-3.5 whitespace-normal">
                          <div className="flex flex-col items-start gap-1">
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

                        <TableCell className="py-3.5 whitespace-normal">
                          {row.signal_ids.length === 0 ? (
                            <span className="text-xs text-muted-foreground">
                              {t.history.noSignals}
                            </span>
                          ) : (
                            <div className="flex flex-wrap gap-1.5">
                              {row.signal_ids.map((sigId) => (
                                <Badge
                                  key={sigId}
                                  variant="outline"
                                  className="h-auto max-w-full whitespace-normal px-2 py-0.5 text-[11px] font-medium"
                                >
                                  {resolveSignalLabel(sigId)}
                                </Badge>
                              ))}
                            </div>
                          )}
                        </TableCell>

                        <TableCell className="pr-4 lg:pr-5 py-3.5 whitespace-normal">
                          <div className="flex flex-col items-start gap-1.5">
                            <div className="flex flex-wrap gap-1">
                              {row.actions.map((act) => (
                                <Badge
                                  key={act}
                                  variant="secondary"
                                  className="h-auto px-2 py-0.5 text-[11px] font-medium"
                                >
                                  {resolveActionLabel(act)}
                                </Badge>
                              ))}
                            </div>
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="text-[11px] text-muted-foreground">
                                {resolveSourceLabel(row.source)}
                              </span>
                              {row.queue_item_id && (
                                <Link
                                  href={getPaymentCheckHref(row.queue_item_id)}
                                  className="inline-flex items-center gap-0.5 text-xs font-semibold text-[var(--brand-text)] hover:underline"
                                >
                                  <span>{t.history.openPayment}</span>
                                  <ArrowUpRight className="size-3.5" />
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
