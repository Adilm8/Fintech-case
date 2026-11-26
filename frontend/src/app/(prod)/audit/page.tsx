"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  AlertTriangle,
  CheckCircle2,
  Inbox,
  Loader2,
  RefreshCw,
  ScrollText,
  Search,
  ShieldAlert,
  ShieldCheck,
  X,
} from "lucide-react";
import { VerdictBadge } from "@/components/VerdictBadge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
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
import { useT } from "@/i18n";
import { formatDateForLang } from "@/lib/format";
import { getAudit, getProdErrorMessage, verifyAudit } from "@/lib/prod/api";
import { RequireRole, useSession } from "@/lib/prod/session";
import type { AuditEntry, AuditVerifyResult } from "@/lib/prod/types";
import { notify } from "@/lib/toast";
import { cn } from "cn";

const AUDIT_ACTIONS = [
  "login",
  "login_failed",
  "logout",
  "payment_created",
  "payment_edited",
  "check",
  "import",
  "sign",
  "sign_denied",
  "send_to_director",
  "decision:approved",
  "decision:approved_trusted",
  "decision:rejected",
  "approval_superseded",
  "postpone",
  "resume",
  "cancel",
  "trust_revoked",
] as const;

const LIMIT_OPTIONS = [50, 100, 250, 500] as const;

function formatTimestamp(iso: string, lang: "ru" | "kk" | "en"): string {
  const datePart = formatDateForLang(iso, lang);
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) {
    return datePart;
  }
  const hh = String(parsed.getHours()).padStart(2, "0");
  const mm = String(parsed.getMinutes()).padStart(2, "0");
  const ss = String(parsed.getSeconds()).padStart(2, "0");
  return `${datePart} ${hh}:${mm}:${ss}`;
}

function summarizeDetails(details: Record<string, unknown>): string {
  const entries = Object.entries(details).filter(
    ([, val]) => val !== null && val !== undefined && val !== ""
  );
  if (entries.length === 0) return "—";
  return entries
    .map(([key, val]) => {
      const formatted =
        typeof val === "object" ? JSON.stringify(val) : String(val);
      return `${key}: ${formatted}`;
    })
    .join(" · ");
}

function actionBadgeClass(action: string): string {
  if (action === "sign_denied" || action === "login_failed") {
    return "border-red-300 bg-red-50 text-red-800";
  }
  if (
    action === "sign" ||
    action === "decision:approved" ||
    action === "decision:approved_trusted"
  ) {
    return "border-[#00AB75]/35 bg-[#E8F8F2] text-[#006B49]";
  }
  if (action === "decision:rejected" || action === "trust_revoked") {
    return "border-amber-300 bg-amber-50 text-amber-900";
  }
  return "border-border bg-muted/60 text-foreground";
}

function AuditPageContent() {
  const searchParams = useSearchParams();
  const initialPaymentId = searchParams.get("payment_id")?.trim() || "";

  const { t, lang, interpolate } = useT();
  const { session } = useSession();

  const [paymentIdInput, setPaymentIdInput] = useState(initialPaymentId);
  const [debouncedPaymentId, setDebouncedPaymentId] =
    useState(initialPaymentId);
  const [actionFilter, setActionFilter] = useState("");
  const [limit, setLimit] = useState<number>(100);

  const [refreshNonce, setRefreshNonce] = useState(0);
  const fetchKey = `${lang}|${limit}|${debouncedPaymentId}|${actionFilter}|${refreshNonce}`;
  const [loadState, setLoadState] = useState<{
    key: string;
    entries: AuditEntry[];
    error: string | null;
  } | null>(null);

  const [isVerifying, setIsVerifying] = useState(false);
  const [verifyResult, setVerifyResult] = useState<AuditVerifyResult | null>(
    null
  );

  const isAnalyst = session?.user.role === "analyst";

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedPaymentId(paymentIdInput.trim());
    }, 250);
    return () => window.clearTimeout(timer);
  }, [paymentIdInput]);

  useEffect(() => {
    const controller = new AbortController();

    getAudit(
      {
        limit,
        payment_id: debouncedPaymentId || undefined,
        action: actionFilter || undefined,
      },
      lang,
      { signal: controller.signal }
    )
      .then((list) => {
        setLoadState({ key: fetchKey, entries: list, error: null });
      })
      .catch((err) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setLoadState((prev) => ({
          key: fetchKey,
          entries: prev?.entries ?? [],
          error: getProdErrorMessage(err),
        }));
      });

    return () => controller.abort();
  }, [actionFilter, debouncedPaymentId, fetchKey, lang, limit]);

  const entries = loadState?.entries ?? [];
  const error = loadState?.error ?? null;
  const isLoading = loadState === null || loadState.key !== fetchKey;

  const handleRefresh = useCallback(() => {
    setRefreshNonce((n) => n + 1);
  }, []);

  const handleVerify = async () => {
    if (!isAnalyst || isVerifying) return;
    setIsVerifying(true);
    try {
      const res = await verifyAudit(lang);
      setVerifyResult(res);
      if (res.ok) {
        notify.success(t.prod.audit.verifyOkTitle);
      } else {
        notify.error(t.prod.audit.verifyBrokenTitle);
      }
    } catch (err) {
      notify.error(t.common.serverErrorTitle, getProdErrorMessage(err));
    } finally {
      setIsVerifying(false);
    }
  };

  const actionLabels: Record<string, string> = t.prod.audit.actions;

  return (
    <div className="space-y-5 sm:space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2.5">
            <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-accent text-[var(--brand-text)]">
              <ScrollText className="size-5" />
            </div>
            <h1 className="text-xl font-semibold tracking-tight text-foreground sm:text-2xl">
              {t.prod.audit.title}
            </h1>
          </div>
          <p className="mt-1.5 text-sm text-muted-foreground">
            {t.prod.audit.subtitle}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {isAnalyst && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void handleVerify()}
              disabled={isVerifying}
              className="min-h-11 gap-1.5 rounded-xl border-[#00AB75]/40 bg-[#E8F8F2]/60 text-[#006B49] hover:bg-[#E8F8F2] sm:min-h-9"
            >
              {isVerifying ? (
                <>
                  <Loader2 className="size-3.5 animate-spin" />
                  <span>{t.prod.audit.verifying}</span>
                </>
              ) : (
                <>
                  <ShieldCheck className="size-3.5" />
                  <span>{t.prod.audit.verifyButton}</span>
                </>
              )}
            </Button>
          )}

          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleRefresh}
            disabled={isLoading}
            className="min-h-11 gap-1.5 rounded-xl sm:min-h-9"
          >
            <RefreshCw className={cn("size-3.5", isLoading && "animate-spin")} />
            <span>{t.common.refresh}</span>
          </Button>
        </div>
      </div>

      {verifyResult && (
        <Alert
          variant={verifyResult.ok ? "default" : "destructive"}
          className={cn(
            "rounded-2xl",
            verifyResult.ok
              ? "border-[#00AB75]/35 bg-[#E8F8F2] text-[#064A34]"
              : "border-red-300 bg-red-50/90"
          )}
        >
          {verifyResult.ok ? (
            <CheckCircle2 className="size-4 text-[var(--brand-text)]" />
          ) : (
            <ShieldAlert className="size-4 text-red-600" />
          )}
          <AlertTitle>
            {verifyResult.ok
              ? t.prod.audit.verifyOkTitle
              : t.prod.audit.verifyBrokenTitle}
          </AlertTitle>
          <AlertDescription className="break-words">
            {verifyResult.ok
              ? interpolate(t.prod.audit.verifyOkDescription, {
                  checked: verifyResult.checked,
                })
              : interpolate(t.prod.audit.verifyBrokenDescription, {
                  id: verifyResult.broken_at ?? "?",
                  checked: verifyResult.checked,
                })}
          </AlertDescription>
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

      <Card className="min-w-0 py-0">
        {/* Filter toolbar */}
        <div className="flex flex-col gap-3 border-b border-border p-4 sm:flex-row sm:flex-wrap sm:items-center sm:px-5">
          <div className="relative flex-1 sm:max-w-xs">
            <Search
              aria-hidden="true"
              className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
            />
            <Input
              type="search"
              value={paymentIdInput}
              onChange={(e) => setPaymentIdInput(e.target.value)}
              placeholder={t.prod.audit.paymentFilterPlaceholder}
              className="h-11 rounded-xl bg-background/70 pl-9 pr-9 font-mono text-xs sm:h-10 [&::-webkit-search-cancel-button]:hidden"
            />
            {paymentIdInput && (
              <button
                type="button"
                onClick={() => {
                  setPaymentIdInput("");
                  setDebouncedPaymentId("");
                }}
                aria-label={t.queue.clearSearch}
                className="absolute top-1/2 right-1.5 flex size-8 -translate-y-1/2 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                <X className="size-4" />
              </button>
            )}
          </div>

          <select
            aria-label={t.prod.audit.colAction}
            value={actionFilter}
            onChange={(e) => setActionFilter(e.target.value)}
            className="h-11 rounded-xl border border-input bg-card px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:h-10"
          >
            <option value="">{t.prod.audit.actionFilterAll}</option>
            {AUDIT_ACTIONS.map((action) => (
              <option key={action} value={action}>
                {actionLabels[action] ?? action}
              </option>
            ))}
          </select>

          <select
            aria-label={t.prod.audit.limitLabel}
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            className="h-11 rounded-xl border border-input bg-card px-3 text-sm tabular-nums text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:h-10"
          >
            {LIMIT_OPTIONS.map((opt) => (
              <option key={opt} value={opt}>
                {t.prod.audit.limitLabel}: {opt}
              </option>
            ))}
          </select>
        </div>

        <CardContent className="p-0">
          {isLoading ? (
            <div className="space-y-3 p-4">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-14 w-full rounded-xl" />
              ))}
            </div>
          ) : entries.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-3 py-14 px-4 text-center">
              <div className="flex size-12 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
                <Inbox className="size-6" />
              </div>
              <div className="space-y-1">
                <div className="text-base font-semibold text-foreground">
                  {t.prod.audit.emptyTitle}
                </div>
                <p className="max-w-md text-sm text-muted-foreground">
                  {t.prod.audit.emptyDescription}
                </p>
              </div>
            </div>
          ) : (
            <>
              {/* Mobile cards */}
              <div className="divide-y divide-border md:hidden">
                {entries.map((entry) => (
                  <div key={entry.id} className="space-y-2 p-4 text-xs">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <Badge
                        variant="outline"
                        className={cn(
                          "h-auto px-2 py-0.5 text-xs font-medium",
                          actionBadgeClass(entry.action)
                        )}
                      >
                        {actionLabels[entry.action] ?? entry.action}
                      </Badge>
                      <span className="font-mono text-muted-foreground tabular-nums">
                        {formatTimestamp(entry.timestamp, lang)}
                      </span>
                    </div>

                    <div className="flex flex-wrap items-center gap-2 text-foreground">
                      <span className="font-medium">
                        {entry.user
                          ? `${entry.user.login} (${t.prod.roles[entry.user.role]})`
                          : t.prod.audit.systemUser}
                      </span>
                      {entry.verdict && <VerdictBadge verdict={entry.verdict} />}
                    </div>

                    {entry.payment_id && (
                      <div>
                        <Link
                          href={`/payments/${entry.payment_id}`}
                          className="font-mono font-medium text-[var(--brand-text)] hover:underline"
                        >
                          {entry.payment_id}
                        </Link>
                      </div>
                    )}

                    <div className="text-muted-foreground break-words">
                      {summarizeDetails(entry.details)}
                    </div>

                    <div
                      className="font-mono text-[11px] text-muted-foreground/80 truncate"
                      title={entry.entry_hash}
                    >
                      #{entry.id} · {entry.entry_hash.slice(0, 16)}…
                    </div>
                  </div>
                ))}
              </div>

              {/* Desktop table */}
              <div className="hidden overflow-x-auto md:block">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-muted/40 hover:bg-muted/40">
                      <TableHead className="w-[155px] pl-4 lg:pl-5">
                        {t.prod.audit.colTime}
                      </TableHead>
                      <TableHead className="w-[165px]">
                        {t.prod.audit.colUser}
                      </TableHead>
                      <TableHead className="w-[195px]">
                        {t.prod.audit.colAction}
                      </TableHead>
                      <TableHead className="w-[130px]">
                        {t.prod.audit.colPayment}
                      </TableHead>
                      <TableHead className="w-[140px]">
                        {t.prod.audit.colVerdict}
                      </TableHead>
                      <TableHead>{t.prod.audit.colDetails}</TableHead>
                      <TableHead className="w-[115px] pr-4 lg:pr-5">
                        {t.prod.audit.colHash}
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {entries.map((entry) => (
                      <TableRow key={entry.id}>
                        <TableCell className="pl-4 lg:pl-5 py-3 align-top font-mono text-xs tabular-nums text-muted-foreground whitespace-nowrap">
                          {formatTimestamp(entry.timestamp, lang)}
                        </TableCell>
                        <TableCell className="py-3 align-top text-xs whitespace-normal">
                          {entry.user ? (
                            <div className="space-y-0.5">
                              <div className="font-medium text-foreground">
                                {entry.user.login}
                              </div>
                              <div className="text-[11px] text-muted-foreground">
                                {t.prod.roles[entry.user.role]}
                              </div>
                            </div>
                          ) : (
                            <span className="text-muted-foreground">
                              {t.prod.audit.systemUser}
                            </span>
                          )}
                        </TableCell>
                        <TableCell className="py-3 align-top whitespace-normal">
                          <Badge
                            variant="outline"
                            className={cn(
                              "h-auto px-2 py-0.5 text-xs font-medium",
                              actionBadgeClass(entry.action)
                            )}
                          >
                            {actionLabels[entry.action] ?? entry.action}
                          </Badge>
                        </TableCell>
                        <TableCell className="py-3 align-top font-mono text-xs whitespace-nowrap">
                          {entry.payment_id ? (
                            <Link
                              href={`/payments/${entry.payment_id}`}
                              className="font-medium text-[var(--brand-text)] hover:underline"
                            >
                              {entry.payment_id}
                            </Link>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </TableCell>
                        <TableCell className="py-3 align-top">
                          {entry.verdict ? (
                            <VerdictBadge verdict={entry.verdict} />
                          ) : (
                            <span className="text-xs text-muted-foreground">
                              —
                            </span>
                          )}
                        </TableCell>
                        <TableCell className="min-w-0 max-w-[300px] py-3 align-top text-xs text-muted-foreground whitespace-normal break-words">
                          {summarizeDetails(entry.details)}
                        </TableCell>
                        <TableCell
                          className="pr-4 lg:pr-5 py-3 align-top font-mono text-[11px] text-muted-foreground whitespace-nowrap"
                          title={entry.entry_hash}
                        >
                          {entry.entry_hash.slice(0, 12)}…
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

export default function ProdAuditPage() {
  return (
    <RequireRole roles={["director", "analyst"]}>
      <Suspense
        fallback={
          <div className="space-y-4">
            <Skeleton className="h-9 w-56" />
            <Skeleton className="h-72 w-full rounded-xl" />
          </div>
        }
      >
        <AuditPageContent />
      </Suspense>
    </RequireRole>
  );
}
