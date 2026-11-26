"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  Building2,
  ChevronRight,
  History,
  Inbox,
  RefreshCw,
  Search,
  SearchX,
  ShieldCheck,
  X,
} from "lucide-react";
import { SupplierBadge } from "@/components/prod/SupplierBadge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
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
import { useT } from "@/i18n";
import { formatIntegerForLang } from "@/lib/format";
import { getProdErrorMessage, getSuppliers } from "@/lib/prod/api";
import { REQUISITES_CHANGED_BADGE_DAYS, type Supplier } from "@/lib/prod/types";
import { cn } from "cn";

function isEditableElement(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") {
    return true;
  }
  return target.isContentEditable;
}

export default function ProdSuppliersPage() {
  const router = useRouter();
  const { t, lang, formatMoney, formatDate, interpolate } = useT();

  const [searchInput, setSearchInput] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [onlyChanged90, setOnlyChanged90] = useState(false);

  const [refreshNonce, setRefreshNonce] = useState(0);
  const fetchKey = `${lang}|${debouncedQuery}|${onlyChanged90}|${refreshNonce}`;
  const [loadState, setLoadState] = useState<{
    key: string;
    suppliers: Supplier[];
    error: string | null;
  } | null>(null);

  const searchInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedQuery(searchInput.trim());
    }, 250);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
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
  }, []);

  useEffect(() => {
    const controller = new AbortController();

    getSuppliers(
      {
        q: debouncedQuery || undefined,
        changed_within_days: onlyChanged90
          ? REQUISITES_CHANGED_BADGE_DAYS
          : undefined,
      },
      lang,
      { signal: controller.signal }
    )
      .then((list) => {
        setLoadState({ key: fetchKey, suppliers: list, error: null });
      })
      .catch((err) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setLoadState((prev) => ({
          key: fetchKey,
          suppliers: prev?.suppliers ?? [],
          error: getProdErrorMessage(err),
        }));
      });

    return () => controller.abort();
  }, [debouncedQuery, fetchKey, lang, onlyChanged90]);

  const suppliers = useMemo(
    () => loadState?.suppliers ?? [],
    [loadState]
  );
  const error = loadState?.error ?? null;
  const isLoading = loadState === null || loadState.key !== fetchKey;

  const handleRefresh = useCallback(() => {
    setRefreshNonce((n) => n + 1);
  }, []);

  const stats = useMemo(() => {
    let changedRecently = 0;
    let pendingChanges = 0;
    let trustedAccounts = 0;
    for (const s of suppliers) {
      if (
        s.requisites_changed_days_ago !== null &&
        s.requisites_changed_days_ago <= REQUISITES_CHANGED_BADGE_DAYS
      ) {
        changedRecently += 1;
      }
      if (s.has_pending_change) {
        pendingChanges += 1;
      }
      trustedAccounts += s.trusted_accounts_count;
    }
    return {
      total: suppliers.length,
      changedRecently,
      pendingChanges,
      trustedAccounts,
    };
  }, [suppliers]);

  const hasFilters = debouncedQuery.length > 0 || onlyChanged90;

  return (
    <div className="space-y-5 sm:space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold tracking-tight text-foreground sm:text-2xl">
            {t.prod.supplier.title}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {t.prod.supplier.subtitle}
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
                {t.prod.supplier.tiles.totalSuppliers}
              </span>
              <div className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-muted text-foreground/75">
                <Building2 className="size-4" />
              </div>
            </div>
            <div className="text-2xl font-bold tabular-nums text-foreground sm:text-3xl">
              {formatIntegerForLang(stats.total, lang)}
            </div>
          </CardContent>
        </Card>

        <Card className="py-4">
          <CardContent className="flex flex-col justify-between gap-2">
            <div className="flex items-start justify-between gap-2">
              <span className="text-xs font-medium text-muted-foreground sm:text-sm">
                {t.prod.supplier.tiles.changedRecently}
              </span>
              <div
                className={cn(
                  "flex size-8 shrink-0 items-center justify-center rounded-xl",
                  stats.changedRecently > 0
                    ? "bg-amber-50 text-amber-700"
                    : "bg-muted text-muted-foreground"
                )}
              >
                <History className="size-4" />
              </div>
            </div>
            <div
              className={cn(
                "text-2xl font-bold tabular-nums sm:text-3xl",
                stats.changedRecently > 0 ? "text-amber-700" : "text-foreground"
              )}
            >
              {formatIntegerForLang(stats.changedRecently, lang)}
            </div>
          </CardContent>
        </Card>

        <Card className="py-4">
          <CardContent className="flex flex-col justify-between gap-2">
            <div className="flex items-start justify-between gap-2">
              <span className="text-xs font-medium text-muted-foreground sm:text-sm">
                {t.prod.supplier.tiles.pendingChanges}
              </span>
              <div
                className={cn(
                  "flex size-8 shrink-0 items-center justify-center rounded-xl",
                  stats.pendingChanges > 0
                    ? "bg-orange-50 text-orange-700"
                    : "bg-muted text-muted-foreground"
                )}
              >
                <AlertTriangle className="size-4" />
              </div>
            </div>
            <div
              className={cn(
                "text-2xl font-bold tabular-nums sm:text-3xl",
                stats.pendingChanges > 0 ? "text-orange-700" : "text-foreground"
              )}
            >
              {formatIntegerForLang(stats.pendingChanges, lang)}
            </div>
          </CardContent>
        </Card>

        <Card className="py-4">
          <CardContent className="flex flex-col justify-between gap-2">
            <div className="flex items-start justify-between gap-2">
              <span className="text-xs font-medium text-muted-foreground sm:text-sm">
                {t.prod.supplier.tiles.trustedAccounts}
              </span>
              <div className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-accent text-[var(--brand-text)]">
                <ShieldCheck className="size-4" />
              </div>
            </div>
            <div className="text-2xl font-bold tabular-nums text-foreground sm:text-3xl">
              {formatIntegerForLang(stats.trustedAccounts, lang)}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Main directory card */}
      <Card className="min-w-0 py-0">
        <div className="flex flex-col gap-3 border-b border-border p-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
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
              placeholder={t.prod.supplier.searchPlaceholder}
              aria-label={t.prod.supplier.searchAriaLabel}
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

          <button
            type="button"
            aria-pressed={onlyChanged90}
            onClick={() => setOnlyChanged90((prev) => !prev)}
            className={cn(
              "inline-flex min-h-11 cursor-pointer items-center justify-center gap-2 rounded-xl border px-3.5 py-2 text-xs font-medium transition-all sm:min-h-9 sm:py-1.5",
              onlyChanged90
                ? "border-amber-300 bg-amber-50 font-semibold text-amber-950 shadow-xs"
                : "border-border bg-card text-foreground hover:bg-muted/70"
            )}
          >
            <History className="size-3.5 shrink-0" />
            <span>{t.prod.supplier.filterChanged90}</span>
          </button>
        </div>

        <CardContent className="p-0">
          {isLoading ? (
            <div className="space-y-3 p-4">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-16 w-full rounded-xl" />
              ))}
            </div>
          ) : suppliers.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-3 py-14 px-4 text-center">
              <div className="flex size-12 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
                {hasFilters ? (
                  <SearchX className="size-6" />
                ) : (
                  <Inbox className="size-6" />
                )}
              </div>
              <div className="space-y-1">
                <div className="text-base font-semibold text-foreground">
                  {hasFilters
                    ? t.prod.supplier.emptyFilteredTitle
                    : t.prod.supplier.emptyTitle}
                </div>
                <p className="max-w-md text-sm text-muted-foreground">
                  {hasFilters
                    ? t.prod.supplier.emptyFilteredDescription
                    : t.prod.supplier.emptyDescription}
                </p>
              </div>
              {hasFilters && (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setSearchInput("");
                    setDebouncedQuery("");
                    setOnlyChanged90(false);
                  }}
                  className="mt-1 min-h-11 rounded-xl sm:min-h-9"
                >
                  {t.queue.resetFilters}
                </Button>
              )}
            </div>
          ) : (
            <>
              {/* Mobile cards (< md) */}
              <div className="flex flex-col gap-3 p-3 sm:p-4 md:hidden">
                {suppliers.map((supplier) => (
                  <Link
                    key={supplier.id}
                    href={`/suppliers/${supplier.id}`}
                    className="block w-full rounded-xl border border-border bg-card p-3.5 text-left shadow-xs transition-all hover:bg-muted/50 active:bg-muted/70"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1 space-y-1">
                        <div className="text-base font-semibold text-foreground break-words">
                          {supplier.name}
                        </div>
                        <div className="font-mono text-xs text-muted-foreground">
                          {interpolate(t.common.binPrefix, {
                            bin: supplier.bin,
                          })}
                        </div>
                      </div>
                      <ChevronRight className="mt-1 size-4 shrink-0 text-muted-foreground" />
                    </div>

                    <div className="mt-2.5 flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                      <span className="font-semibold text-sm tabular-nums text-foreground">
                        {formatMoney(supplier.total_paid_kzt)}
                      </span>
                      <span className="tabular-nums">
                        {t.prod.supplier.colAccounts}: {supplier.accounts_count}{" "}
                        · {t.prod.supplier.colPayments}:{" "}
                        {supplier.payments_count}
                      </span>
                    </div>

                    {supplier.last_payment_at && (
                      <div className="mt-1 text-xs text-muted-foreground">
                        {t.prod.supplier.colLastPayment}:{" "}
                        {formatDate(supplier.last_payment_at)}
                      </div>
                    )}

                    <SupplierBadge
                      requisitesChangedDaysAgo={
                        supplier.requisites_changed_days_ago
                      }
                      hasPendingChange={supplier.has_pending_change}
                      trustedAccountsCount={supplier.trusted_accounts_count}
                      className="mt-2.5"
                    />
                  </Link>
                ))}
              </div>

              {/* Desktop table (>= md) */}
              <div className="hidden overflow-x-auto md:block">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-muted/40 hover:bg-muted/40">
                      <TableHead className="pl-4 lg:pl-5">
                        {t.prod.supplier.colSupplier}
                      </TableHead>
                      <TableHead className="w-[90px] text-right">
                        {t.prod.supplier.colAccounts}
                      </TableHead>
                      <TableHead className="w-[100px] text-right">
                        {t.prod.supplier.colPayments}
                      </TableHead>
                      <TableHead className="w-[155px] text-right">
                        {t.prod.supplier.colTotalPaid}
                      </TableHead>
                      <TableHead className="w-[135px]">
                        {t.prod.supplier.colLastPayment}
                      </TableHead>
                      <TableHead className="w-[260px]">
                        {t.prod.supplier.colRequisitesStatus}
                      </TableHead>
                      <TableHead className="w-9 pr-3 lg:pr-4" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {suppliers.map((supplier) => (
                      <TableRow
                        key={supplier.id}
                        tabIndex={0}
                        role="link"
                        onClick={() => router.push(`/suppliers/${supplier.id}`)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            router.push(`/suppliers/${supplier.id}`);
                          }
                        }}
                        className="cursor-pointer transition-colors hover:bg-muted/45 focus-visible:bg-accent/50 focus-visible:outline-none"
                      >
                        <TableCell className="min-w-0 max-w-[300px] pl-4 lg:pl-5 py-3.5 align-top whitespace-normal">
                          <div className="font-semibold text-foreground break-words">
                            {supplier.name}
                          </div>
                          <div className="font-mono text-xs text-muted-foreground">
                            {interpolate(t.common.binPrefix, {
                              bin: supplier.bin,
                            })}
                          </div>
                        </TableCell>

                        <TableCell className="py-3.5 align-top text-right tabular-nums">
                          {formatIntegerForLang(supplier.accounts_count, lang)}
                        </TableCell>

                        <TableCell className="py-3.5 align-top text-right tabular-nums">
                          {formatIntegerForLang(supplier.payments_count, lang)}
                        </TableCell>

                        <TableCell className="py-3.5 align-top text-right font-semibold tabular-nums whitespace-nowrap">
                          {formatMoney(supplier.total_paid_kzt)}
                        </TableCell>

                        <TableCell className="py-3.5 align-top text-xs text-muted-foreground whitespace-nowrap">
                          {supplier.last_payment_at
                            ? formatDate(supplier.last_payment_at)
                            : "—"}
                        </TableCell>

                        <TableCell className="py-3.5 align-top whitespace-normal">
                          <SupplierBadge
                            requisitesChangedDaysAgo={
                              supplier.requisites_changed_days_ago
                            }
                            hasPendingChange={supplier.has_pending_change}
                            trustedAccountsCount={
                              supplier.trusted_accounts_count
                            }
                          />
                        </TableCell>

                        <TableCell className="pr-3 lg:pr-4 py-3.5 align-middle text-right">
                          <ChevronRight className="ml-auto size-4 text-muted-foreground" />
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
