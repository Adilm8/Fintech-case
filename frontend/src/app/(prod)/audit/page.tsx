"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { AlertTriangle, Loader2, RefreshCw, Search, X } from "lucide-react";
import { VerdictBadge } from "@/components/VerdictBadge";
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
  "profile_updated",
  "password_changed",
  "password_change_failed",
  "user_invited",
  "company_user_updated",
  "company_settings_updated",
  "notifications_read",
  "payments_exported",
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

function actionTone(action: string): { dotClass: string; textClass?: string } {
  if (
    action === "sign_denied" ||
    action === "login_failed" ||
    action === "password_change_failed"
  ) {
    return {
      dotClass: "ui-dot-danger",
      textClass: "text-[var(--status-danger-text)]",
    };
  }
  if (
    action === "sign" ||
    action === "decision:approved" ||
    action === "decision:approved_trusted"
  ) {
    return { dotClass: "ui-dot-ok" };
  }
  if (action === "decision:rejected" || action === "trust_revoked") {
    return { dotClass: "ui-dot-warn" };
  }
  return { dotClass: "ui-dot-neutral" };
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
    <div className="space-y-4 sm:space-y-5">
      <div className="ui-page-header">
        <div className="min-w-0">
          <h1 className="ui-page-title">{t.prod.audit.title}</h1>
          <p className="ui-page-subtitle">{t.prod.audit.subtitle}</p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {isAnalyst && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void handleVerify()}
              disabled={isVerifying}
              className="min-h-10 sm:min-h-8"
            >
              {isVerifying ? (
                <>
                  <Loader2 className="size-3.5 animate-spin" />
                  <span>{t.prod.audit.verifying}</span>
                </>
              ) : (
                <span>{t.prod.audit.verifyButton}</span>
              )}
            </Button>
          )}

          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleRefresh}
            disabled={isLoading}
            className="min-h-10 gap-1.5 sm:min-h-8"
          >
            <RefreshCw className={cn("size-3.5", isLoading && "animate-spin")} />
            <span>{t.common.refresh}</span>
          </Button>
        </div>
      </div>

      {verifyResult && (
        <div
          role="status"
          className={cn(
            "ui-notice space-y-0.5",
            verifyResult.ok ? "ui-notice-ok" : "ui-notice-danger"
          )}
        >
          <div className="text-sm font-semibold text-foreground">
            {verifyResult.ok
              ? t.prod.audit.verifyOkTitle
              : t.prod.audit.verifyBrokenTitle}
          </div>
          <p className="text-xs text-muted-foreground tabular-nums break-words">
            {verifyResult.ok
              ? interpolate(t.prod.audit.verifyOkDescription, {
                  checked: verifyResult.checked,
                })
              : interpolate(t.prod.audit.verifyBrokenDescription, {
                  id: verifyResult.broken_at ?? "?",
                  checked: verifyResult.checked,
                })}
          </p>
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

      <Card className="min-w-0 py-0">
        {/* Filter toolbar */}
        <div className="flex flex-col gap-3 border-b border-border p-4 sm:flex-row sm:flex-wrap sm:items-center">
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
              className="h-10 rounded-[6px] bg-card pl-9 pr-9 font-mono text-base sm:h-9 sm:text-xs [&::-webkit-search-cancel-button]:hidden"
            />
            {paymentIdInput && (
              <button
                type="button"
                onClick={() => {
                  setPaymentIdInput("");
                  setDebouncedPaymentId("");
                }}
                aria-label={t.queue.clearSearch}
                className="absolute top-1/2 right-1.5 flex size-8 -translate-y-1/2 items-center justify-center rounded-[4px] text-muted-foreground hover:bg-muted hover:text-foreground sm:size-7"
              >
                <X className="size-4" />
              </button>
            )}
          </div>

          <select
            aria-label={t.prod.audit.colAction}
            value={actionFilter}
            onChange={(e) => setActionFilter(e.target.value)}
            className="ui-select"
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
            className="ui-select tabular-nums"
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
                <Skeleton key={i} className="h-12 w-full rounded-[6px]" />
              ))}
            </div>
          ) : entries.length === 0 ? (
            <div className="ui-empty">
              <div className="ui-empty-title">{t.prod.audit.emptyTitle}</div>
              <p className="ui-empty-desc">{t.prod.audit.emptyDescription}</p>
            </div>
          ) : (
            <>
              {/* Mobile flat list */}
              <div className="divide-y divide-border md:hidden">
                {entries.map((entry) => {
                  const tone = actionTone(entry.action);
                  return (
                    <div key={entry.id} className="space-y-2 p-4 text-xs">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className={cn("ui-status", tone.textClass)}>
                          <span
                            aria-hidden="true"
                            className={cn("ui-status-dot", tone.dotClass)}
                          />
                          <span>
                            {actionLabels[entry.action] ?? entry.action}
                          </span>
                        </span>
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
                        {entry.verdict && (
                          <VerdictBadge verdict={entry.verdict} />
                        )}
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
                        className="font-mono text-[11px] tabular-nums text-muted-foreground truncate"
                        title={entry.entry_hash}
                      >
                        #{entry.id} · {entry.entry_hash.slice(0, 16)}…
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Desktop table */}
              <div className="hidden overflow-x-auto md:block">
                <Table>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent">
                      <TableHead className="w-[155px] pl-4">
                        {t.prod.audit.colTime}
                      </TableHead>
                      <TableHead className="w-[165px]">
                        {t.prod.audit.colUser}
                      </TableHead>
                      <TableHead className="w-[210px]">
                        {t.prod.audit.colAction}
                      </TableHead>
                      <TableHead className="w-[130px]">
                        {t.prod.audit.colPayment}
                      </TableHead>
                      <TableHead className="w-[140px]">
                        {t.prod.audit.colVerdict}
                      </TableHead>
                      <TableHead>{t.prod.audit.colDetails}</TableHead>
                      <TableHead className="w-[115px] pr-4">
                        {t.prod.audit.colHash}
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {entries.map((entry) => {
                      const tone = actionTone(entry.action);
                      return (
                        <TableRow key={entry.id}>
                          <TableCell className="pl-4 py-2.5 align-top font-mono text-xs tabular-nums text-muted-foreground whitespace-nowrap">
                            {formatTimestamp(entry.timestamp, lang)}
                          </TableCell>
                          <TableCell className="py-2.5 align-top text-xs whitespace-normal">
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
                          <TableCell className="py-2.5 align-top whitespace-normal">
                            <span className={cn("ui-status", tone.textClass)}>
                              <span
                                aria-hidden="true"
                                className={cn("ui-status-dot", tone.dotClass)}
                              />
                              <span>
                                {actionLabels[entry.action] ?? entry.action}
                              </span>
                            </span>
                          </TableCell>
                          <TableCell className="py-2.5 align-top font-mono text-xs whitespace-nowrap">
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
                          <TableCell className="py-2.5 align-top">
                            {entry.verdict ? (
                              <VerdictBadge verdict={entry.verdict} />
                            ) : (
                              <span className="text-xs text-muted-foreground">
                                —
                              </span>
                            )}
                          </TableCell>
                          <TableCell className="min-w-0 max-w-[300px] py-2.5 align-top text-xs text-muted-foreground whitespace-normal break-words">
                            {summarizeDetails(entry.details)}
                          </TableCell>
                          <TableCell
                            className="pr-4 py-2.5 align-top font-mono text-[11px] tabular-nums text-muted-foreground whitespace-nowrap"
                            title={entry.entry_hash}
                          >
                            {entry.entry_hash.slice(0, 12)}…
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
    </div>
  );
}

export default function ProdAuditPage() {
  return (
    <RequireRole roles={["director", "analyst"]}>
      <Suspense
        fallback={
          <div className="space-y-4">
            <Skeleton className="h-7 w-56 rounded-[6px]" />
            <Skeleton className="h-72 w-full rounded-[8px]" />
          </div>
        }
      >
        <AuditPageContent />
      </Suspense>
    </RequireRole>
  );
}
