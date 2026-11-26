"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { AlertCircle, AlertTriangle, ArrowLeft, Loader2 } from "lucide-react";
import { PaymentsTable } from "@/components/prod/PaymentsTable";
import { SupplierBadge } from "@/components/prod/SupplierBadge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { useT } from "@/i18n";
import { formatIntegerForLang } from "@/lib/format";
import {
  ApiError,
  getProdErrorMessage,
  getSupplier,
  untrustSupplierAccount,
} from "@/lib/prod/api";
import { useSession } from "@/lib/prod/session";
import {
  MIN_DIRECTOR_COMMENT_LENGTH,
  type SupplierAccount,
  type SupplierDetail,
} from "@/lib/prod/types";
import { notify } from "@/lib/toast";
import { cn } from "cn";

export default function ProdSupplierDetailPage() {
  const params = useParams<{ id: string }>();
  const supplierId = typeof params?.id === "string" ? params.id : "";
  const { t, lang, formatMoney, formatDate, interpolate, plural } = useT();
  const { session } = useSession();

  const fetchKey = `${supplierId}|${lang}`;
  const [loadState, setLoadState] = useState<{
    key: string;
    supplier: SupplierDetail | null;
    notFound: boolean;
    error: string | null;
  } | null>(null);

  const [untrustTarget, setUntrustTarget] = useState<SupplierAccount | null>(
    null
  );
  const [untrustComment, setUntrustComment] = useState("");
  const [untrustError, setUntrustError] = useState<string | null>(null);
  const [isUntrusting, setIsUntrusting] = useState(false);

  const isDirector = session?.user.role === "director";

  const reloadSupplier = useCallback(async () => {
    if (!supplierId) return;
    try {
      const data = await getSupplier(supplierId, lang);
      setLoadState({
        key: fetchKey,
        supplier: data,
        notFound: false,
        error: null,
      });
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setLoadState({
          key: fetchKey,
          supplier: null,
          notFound: true,
          error: null,
        });
      } else {
        setLoadState((prev) => ({
          key: fetchKey,
          supplier: prev?.supplier ?? null,
          notFound: false,
          error: getProdErrorMessage(err),
        }));
      }
    }
  }, [fetchKey, lang, supplierId]);

  useEffect(() => {
    if (!supplierId) return;
    const controller = new AbortController();

    getSupplier(supplierId, lang, { signal: controller.signal })
      .then((data) => {
        setLoadState({
          key: fetchKey,
          supplier: data,
          notFound: false,
          error: null,
        });
      })
      .catch((err) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        if (err instanceof ApiError && err.status === 404) {
          setLoadState({
            key: fetchKey,
            supplier: null,
            notFound: true,
            error: null,
          });
        } else {
          setLoadState((prev) => ({
            key: fetchKey,
            supplier: prev?.supplier ?? null,
            notFound: false,
            error: getProdErrorMessage(err),
          }));
        }
      });

    return () => controller.abort();
  }, [fetchKey, lang, supplierId]);

  const supplier = loadState?.supplier ?? null;
  const notFoundError = Boolean(loadState?.notFound);
  const error = loadState?.error ?? null;
  const isLoading = loadState === null || loadState.key !== fetchKey;

  const minCharsLabel = plural(
    MIN_DIRECTOR_COMMENT_LENGTH,
    t.plurals.charsGenitive
  );
  const trimmedUntrustComment = untrustComment.trim();
  const untrustTooShort =
    trimmedUntrustComment.length < MIN_DIRECTOR_COMMENT_LENGTH;

  const handleUntrustSubmit = async () => {
    if (!supplier || !untrustTarget || untrustTooShort || isUntrusting) return;
    setUntrustError(null);
    setIsUntrusting(true);
    try {
      const updated = await untrustSupplierAccount(
        supplier.id,
        untrustTarget.id,
        trimmedUntrustComment,
        lang
      );
      setLoadState({
        key: fetchKey,
        supplier: updated,
        notFound: false,
        error: null,
      });
      setUntrustTarget(null);
      setUntrustComment("");
      notify.success(t.prod.supplier.detail.untrustSuccess);
    } catch (err) {
      setUntrustError(getProdErrorMessage(err));
    } finally {
      setIsUntrusting(false);
    }
  };

  if (isLoading && !supplier) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-40 rounded-[6px]" />
        <Skeleton className="h-36 w-full rounded-[8px]" />
        <Skeleton className="h-52 w-full rounded-[8px]" />
        <Skeleton className="h-44 w-full rounded-[8px]" />
      </div>
    );
  }

  if (notFoundError) {
    return (
      <div className="space-y-4">
        <Link
          href="/suppliers"
          className={cn(
            buttonVariants({ variant: "ghost", size: "sm" }),
            "min-h-11 gap-1.5 text-muted-foreground hover:text-foreground sm:min-h-8"
          )}
        >
          <ArrowLeft className="size-4" />
          <span>{t.prod.supplier.backToSuppliers}</span>
        </Link>

        <div className="ui-panel">
          <div className="ui-empty">
            <div className="ui-empty-title">
              {t.prod.supplier.notFoundTitle}
            </div>
            <p className="ui-empty-desc">
              {t.prod.supplier.notFoundDescription}
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (error && !supplier) {
    return (
      <div className="space-y-4">
        <Link
          href="/suppliers"
          className={cn(
            buttonVariants({ variant: "ghost", size: "sm" }),
            "min-h-11 gap-1.5 text-muted-foreground hover:text-foreground sm:min-h-8"
          )}
        >
          <ArrowLeft className="size-4" />
          <span>{t.prod.supplier.backToSuppliers}</span>
        </Link>

        <Alert variant="destructive" className="ui-notice ui-notice-danger">
          <AlertTriangle className="size-4" />
          <AlertTitle>{t.common.serverErrorTitle}</AlertTitle>
          <AlertDescription className="flex flex-wrap items-center justify-between gap-2 break-words">
            <span>{error}</span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void reloadSupplier()}
              className="min-h-10 sm:min-h-8"
            >
              {t.common.retry}
            </Button>
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  if (!supplier) return null;

  return (
    <div className="space-y-4 sm:space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2.5">
        <Link
          href="/suppliers"
          className={cn(
            buttonVariants({ variant: "ghost", size: "sm" }),
            "min-h-11 gap-1.5 text-muted-foreground hover:text-foreground sm:min-h-8"
          )}
        >
          <ArrowLeft className="size-4" />
          <span>{t.prod.supplier.backToSuppliers}</span>
        </Link>

        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => void reloadSupplier()}
          disabled={isLoading}
          className="min-h-10 sm:min-h-8"
        >
          {isLoading && <Loader2 className="size-3.5 animate-spin" />}
          <span>{t.common.refresh}</span>
        </Button>
      </div>

      {/* Supplier overview */}
      <div className="ui-panel min-w-0 p-4 space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 space-y-1.5">
            <h1 className="ui-page-title break-words">{supplier.name}</h1>
            <SupplierBadge
              requisitesChangedDaysAgo={supplier.requisites_changed_days_ago}
              hasPendingChange={supplier.has_pending_change}
              trustedAccountsCount={supplier.trusted_accounts_count}
            />
          </div>

          <div className="shrink-0 text-left sm:text-right">
            <div className="ui-label-meta">
              {t.prod.supplier.detail.totalPaid}
            </div>
            <div className="mt-0.5 text-[22px] leading-7 font-semibold tabular-nums whitespace-nowrap text-foreground">
              {formatMoney(supplier.total_paid_kzt)}
            </div>
          </div>
        </div>

        <dl className="ui-dl">
          <div className="ui-dl-row">
            <dt className="ui-dt">{t.prod.company.binLabel}</dt>
            <dd className="ui-dd font-mono tabular-nums">{supplier.bin}</dd>
          </div>
          <div className="ui-dl-row">
            <dt className="ui-dt">{t.prod.supplier.detail.paymentsCount}</dt>
            <dd className="ui-dd font-medium tabular-nums">
              {formatIntegerForLang(supplier.payments_count, lang)}
            </dd>
          </div>
          <div className="ui-dl-row">
            <dt className="ui-dt">{t.prod.supplier.detail.firstSeen}</dt>
            <dd className="ui-dd tabular-nums">
              {formatDate(supplier.first_seen_at)}
            </dd>
          </div>
          <div className="ui-dl-row">
            <dt className="ui-dt">{t.prod.supplier.detail.lastPayment}</dt>
            <dd className="ui-dd tabular-nums">
              {supplier.last_payment_at
                ? formatDate(supplier.last_payment_at)
                : "—"}
            </dd>
          </div>
        </dl>
      </div>

      {/* Accounts section */}
      <Card className="min-w-0 py-0">
        <CardHeader className="border-b border-border py-3.5">
          <CardTitle>{t.prod.supplier.detail.accountsTitle}</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {supplier.accounts.length === 0 ? (
            <div className="ui-empty">
              <p className="ui-empty-desc">
                {t.prod.supplier.detail.accountsEmpty}
              </p>
            </div>
          ) : (
            <>
              {/* Mobile list */}
              <div className="divide-y divide-border md:hidden">
                {supplier.accounts.map((acc) => (
                  <div key={acc.id} className="space-y-2.5 p-4">
                    <div className="space-y-0.5">
                      <div className="font-mono text-sm font-medium break-all tabular-nums text-foreground">
                        {acc.iik}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        <span className="font-mono">{acc.bik}</span>
                        {acc.bank_name ? ` · ${acc.bank_name}` : ""}
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground tabular-nums">
                      <span>
                        {interpolate(t.prod.supplier.detail.periodRange, {
                          first: formatDate(acc.first_seen_at),
                          last: formatDate(acc.last_used_at),
                        })}
                      </span>
                      <span>
                        {interpolate(t.prod.supplier.detail.paymentsCountShort, {
                          count: formatIntegerForLang(acc.payments_count, lang),
                        })}
                      </span>
                    </div>

                    <div className="flex flex-wrap items-center justify-between gap-2">
                      {acc.trusted ? (
                        <div className="space-y-1">
                          <span className="ui-status text-[var(--status-ok-text)]">
                            <span
                              aria-hidden="true"
                              className="ui-status-dot ui-dot-ok"
                            />
                            <span>{t.prod.supplier.detail.trustedStatus}</span>
                          </span>
                          {acc.trusted_at && (
                            <div className="text-xs text-muted-foreground tabular-nums">
                              {interpolate(t.prod.supplier.detail.trustedSince, {
                                date: formatDate(acc.trusted_at),
                              })}
                            </div>
                          )}
                          {acc.trusted_comment && (
                            <div className="text-xs text-muted-foreground break-words">
                              {acc.trusted_comment}
                            </div>
                          )}
                        </div>
                      ) : (
                        <span className="ui-status text-muted-foreground">
                          <span
                            aria-hidden="true"
                            className="ui-status-dot ui-dot-neutral"
                          />
                          <span>{t.prod.supplier.detail.notTrustedStatus}</span>
                        </span>
                      )}

                      {isDirector && acc.trusted && (
                        <Button
                          type="button"
                          variant="destructive"
                          size="sm"
                          onClick={() => {
                            setUntrustTarget(acc);
                            setUntrustComment("");
                            setUntrustError(null);
                          }}
                          className="min-h-10 sm:min-h-8"
                        >
                          {t.prod.supplier.detail.untrustButton}
                        </Button>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              {/* Desktop table */}
              <div className="hidden overflow-x-auto md:block">
                <Table>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent">
                      <TableHead className="pl-4">
                        {t.prod.supplier.detail.colIik}
                      </TableHead>
                      <TableHead>{t.prod.supplier.detail.colBank}</TableHead>
                      <TableHead>{t.prod.supplier.detail.colPeriod}</TableHead>
                      <TableHead className="pr-4">
                        {t.prod.supplier.detail.colTrust}
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {supplier.accounts.map((acc) => (
                      <TableRow key={acc.id}>
                        <TableCell className="pl-4 align-top whitespace-normal">
                          <div className="font-mono text-sm font-medium break-all tabular-nums">
                            {acc.iik}
                          </div>
                          <div className="font-mono text-xs text-muted-foreground">
                            {acc.bik}
                          </div>
                        </TableCell>
                        <TableCell className="align-top text-sm whitespace-normal">
                          {acc.bank_name || "—"}
                        </TableCell>
                        <TableCell className="align-top text-xs text-muted-foreground tabular-nums whitespace-normal">
                          <div>
                            {interpolate(t.prod.supplier.detail.periodRange, {
                              first: formatDate(acc.first_seen_at),
                              last: formatDate(acc.last_used_at),
                            })}
                          </div>
                          <div className="mt-0.5">
                            {interpolate(
                              t.prod.supplier.detail.paymentsCountShort,
                              {
                                count: formatIntegerForLang(
                                  acc.payments_count,
                                  lang
                                ),
                              }
                            )}
                          </div>
                        </TableCell>
                        <TableCell className="pr-4 align-top whitespace-normal">
                          <div className="flex flex-wrap items-start justify-between gap-2">
                            <div className="space-y-1">
                              {acc.trusted ? (
                                <>
                                  <span className="ui-status text-[var(--status-ok-text)]">
                                    <span
                                      aria-hidden="true"
                                      className="ui-status-dot ui-dot-ok"
                                    />
                                    <span>
                                      {t.prod.supplier.detail.trustedStatus}
                                    </span>
                                  </span>
                                  {acc.trusted_at && (
                                    <div className="text-xs text-muted-foreground tabular-nums">
                                      {interpolate(
                                        t.prod.supplier.detail.trustedSince,
                                        { date: formatDate(acc.trusted_at) }
                                      )}
                                    </div>
                                  )}
                                  {acc.trusted_comment && (
                                    <div className="max-w-xs text-xs text-muted-foreground break-words">
                                      {acc.trusted_comment}
                                    </div>
                                  )}
                                </>
                              ) : (
                                <span className="ui-status text-muted-foreground">
                                  <span
                                    aria-hidden="true"
                                    className="ui-status-dot ui-dot-neutral"
                                  />
                                  <span>
                                    {t.prod.supplier.detail.notTrustedStatus}
                                  </span>
                                </span>
                              )}
                            </div>

                            {isDirector && acc.trusted && (
                              <Button
                                type="button"
                                variant="destructive"
                                size="sm"
                                onClick={() => {
                                  setUntrustTarget(acc);
                                  setUntrustComment("");
                                  setUntrustError(null);
                                }}
                                className="min-h-8"
                              >
                                {t.prod.supplier.detail.untrustButton}
                              </Button>
                            )}
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

      {/* Requisites change timeline */}
      <Card className="min-w-0 py-0">
        <CardHeader className="border-b border-border py-3.5">
          <CardTitle>{t.prod.supplier.detail.changesTitle}</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {supplier.changes.length === 0 ? (
            <div className="ui-empty">
              <p className="ui-empty-desc">
                {t.prod.supplier.detail.changesEmpty}
              </p>
            </div>
          ) : (
            <>
              {/* Mobile list (< md) */}
              <div className="divide-y divide-border md:hidden">
                {supplier.changes.map((change) => (
                  <div key={change.id} className="space-y-1.5 px-4 py-3 text-xs">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="ui-status">
                        <span
                          aria-hidden="true"
                          className="ui-status-dot ui-dot-warn"
                        />
                        <span>{t.prod.supplier.changeKinds[change.kind]}</span>
                      </span>
                      <span className="text-muted-foreground tabular-nums">
                        {formatDate(change.occurred_at)}
                      </span>
                    </div>
                    {change.old_value && (
                      <div className="text-muted-foreground break-all">
                        <span>{t.prod.supplier.detail.wasLabel}: </span>
                        <span className="font-mono text-foreground">
                          {change.old_value}
                        </span>
                      </div>
                    )}
                    <div className="text-muted-foreground break-all">
                      <span>{t.prod.supplier.detail.becameLabel}: </span>
                      <span className="font-mono font-medium text-foreground">
                        {change.new_value}
                      </span>
                    </div>
                    {change.payment_id && (
                      <div>
                        <Link
                          href={`/payments/${change.payment_id}`}
                          className="font-medium text-[var(--brand-text)] hover:underline"
                        >
                          {t.prod.supplier.detail.openPayment}
                        </Link>
                      </div>
                    )}
                  </div>
                ))}
              </div>

              {/* Dense desktop table (>= md) */}
              <div className="hidden overflow-x-auto md:block">
                <Table>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent">
                      <TableHead className="w-[120px] pl-4">
                        {t.prod.audit.colTime}
                      </TableHead>
                      <TableHead className="w-[210px]">
                        {t.prod.audit.colAction}
                      </TableHead>
                      <TableHead>{t.prod.supplier.detail.wasLabel}</TableHead>
                      <TableHead>{t.prod.supplier.detail.becameLabel}</TableHead>
                      <TableHead className="w-[110px] pr-4 text-right">
                        {t.prod.supplier.detail.openPayment}
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {supplier.changes.map((change) => (
                      <TableRow key={change.id}>
                        <TableCell className="pl-4 align-top text-xs text-muted-foreground tabular-nums whitespace-nowrap">
                          {formatDate(change.occurred_at)}
                        </TableCell>
                        <TableCell className="align-top whitespace-normal">
                          <span className="ui-status">
                            <span
                              aria-hidden="true"
                              className="ui-status-dot ui-dot-warn"
                            />
                            <span>
                              {t.prod.supplier.changeKinds[change.kind]}
                            </span>
                          </span>
                        </TableCell>
                        <TableCell className="align-top font-mono text-xs text-muted-foreground whitespace-normal break-all">
                          {change.old_value || "—"}
                        </TableCell>
                        <TableCell className="align-top font-mono text-xs font-medium text-foreground whitespace-normal break-all">
                          {change.new_value}
                        </TableCell>
                        <TableCell className="pr-4 align-top text-right text-xs whitespace-nowrap">
                          {change.payment_id ? (
                            <Link
                              href={`/payments/${change.payment_id}`}
                              className="font-medium text-[var(--brand-text)] hover:underline"
                            >
                              {t.prod.supplier.detail.openPayment}
                            </Link>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
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

      {/* Recent payments */}
      <Card className="min-w-0 py-0">
        <CardHeader className="border-b border-border py-3.5">
          <CardTitle>{t.prod.supplier.detail.paymentsTitle}</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {supplier.payments.length === 0 ? (
            <div className="ui-empty">
              <p className="ui-empty-desc">
                {t.prod.supplier.detail.paymentsEmpty}
              </p>
            </div>
          ) : (
            <PaymentsTable payments={supplier.payments} />
          )}
        </CardContent>
      </Card>

      {/* Untrust account dialog (Director only, F8) */}
      <Dialog
        open={untrustTarget !== null}
        onOpenChange={(nextOpen) => {
          if (!nextOpen && !isUntrusting) {
            setUntrustTarget(null);
            setUntrustError(null);
          }
        }}
      >
        <DialogContent mobileSheet className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              {t.prod.supplier.detail.untrustDialogTitle}
            </DialogTitle>
            {untrustTarget && (
              <DialogDescription>
                {interpolate(t.prod.supplier.detail.untrustDialogDescription, {
                  iik: untrustTarget.iik,
                })}
              </DialogDescription>
            )}
          </DialogHeader>

          <div className="space-y-3">
            {untrustError && (
              <Alert variant="destructive">
                <AlertCircle className="size-4" />
                <AlertDescription className="break-words">
                  {untrustError}
                </AlertDescription>
              </Alert>
            )}

            <div className="space-y-1.5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Label htmlFor="untrust-comment-input">
                  {t.prod.supplier.detail.untrustCommentLabel}
                  <span className="ml-1 font-semibold text-[var(--status-danger-text)]">
                    *
                  </span>
                </Label>
                <span
                  className={cn(
                    "text-xs font-medium tabular-nums",
                    untrustTooShort
                      ? "text-[var(--status-danger-text)]"
                      : "text-[var(--status-ok-text)]"
                  )}
                >
                  {interpolate(t.prod.supplier.detail.untrustCommentRequired, {
                    minChars: minCharsLabel,
                    current: trimmedUntrustComment.length,
                    min: MIN_DIRECTOR_COMMENT_LENGTH,
                  })}
                </span>
              </div>
              <Textarea
                id="untrust-comment-input"
                rows={3}
                value={untrustComment}
                onChange={(e) => {
                  setUntrustComment(e.target.value);
                  if (untrustError) setUntrustError(null);
                }}
                placeholder={interpolate(
                  t.prod.supplier.detail.untrustCommentPlaceholder,
                  { minChars: minCharsLabel }
                )}
                disabled={isUntrusting}
                className="min-h-24"
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setUntrustTarget(null)}
              disabled={isUntrusting}
              className="min-h-11 w-full sm:min-h-9 sm:w-auto"
            >
              {t.common.cancel}
            </Button>
            <Button
              type="button"
              variant="destructive"
              disabled={untrustTooShort || isUntrusting}
              onClick={() => void handleUntrustSubmit()}
              className="min-h-11 w-full sm:min-h-9 sm:w-auto"
            >
              {isUntrusting ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  <span>{t.prod.supplier.detail.untrusting}</span>
                </>
              ) : (
                <span>{t.prod.supplier.detail.untrustConfirm}</span>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
