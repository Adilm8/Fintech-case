"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  Building2,
  History,
  Inbox,
  Loader2,
  RefreshCw,
  ShieldCheck,
  ShieldOff,
} from "lucide-react";
import { PaymentsTable } from "@/components/prod/PaymentsTable";
import { SupplierBadge } from "@/components/prod/SupplierBadge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
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
      <div className="space-y-5">
        <Skeleton className="h-9 w-40 rounded-lg" />
        <Skeleton className="h-36 w-full rounded-xl" />
        <Skeleton className="h-52 w-full rounded-xl" />
        <Skeleton className="h-44 w-full rounded-xl" />
      </div>
    );
  }

  if (notFoundError) {
    return (
      <div className="space-y-5">
        <Link
          href="/suppliers"
          className={cn(
            buttonVariants({ variant: "ghost", size: "sm" }),
            "min-h-11 gap-1.5 text-muted-foreground hover:text-foreground sm:min-h-9"
          )}
        >
          <ArrowLeft className="size-4" />
          <span>{t.prod.supplier.backToSuppliers}</span>
        </Link>

        <Card>
          <CardContent className="flex flex-col items-center justify-center gap-3 py-16 px-4 text-center">
            <div className="flex size-12 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
              <Inbox className="size-6" />
            </div>
            <div className="space-y-1">
              <div className="text-base font-semibold text-foreground">
                {t.prod.supplier.notFoundTitle}
              </div>
              <p className="max-w-md text-sm text-muted-foreground">
                {t.prod.supplier.notFoundDescription}
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (error && !supplier) {
    return (
      <div className="space-y-5">
        <Link
          href="/suppliers"
          className={cn(
            buttonVariants({ variant: "ghost", size: "sm" }),
            "min-h-11 gap-1.5 text-muted-foreground hover:text-foreground sm:min-h-9"
          )}
        >
          <ArrowLeft className="size-4" />
          <span>{t.prod.supplier.backToSuppliers}</span>
        </Link>

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
              onClick={() => void reloadSupplier()}
              className="gap-1.5 border-red-300 bg-white text-red-900 hover:bg-red-50"
            >
              <RefreshCw className="size-3.5" />
              <span>{t.common.retry}</span>
            </Button>
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  if (!supplier) return null;

  return (
    <div className="space-y-5 sm:space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2.5">
        <Link
          href="/suppliers"
          className={cn(
            buttonVariants({ variant: "ghost", size: "sm" }),
            "min-h-11 gap-1.5 text-muted-foreground hover:text-foreground sm:min-h-9"
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
          className="min-h-10 gap-1.5 rounded-xl sm:min-h-9"
        >
          <RefreshCw className={cn("size-3.5", isLoading && "animate-spin")} />
          <span>{t.common.refresh}</span>
        </Button>
      </div>

      {/* Supplier overview */}
      <Card className="min-w-0">
        <CardContent className="space-y-4 py-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0 space-y-1.5">
              <div className="flex items-center gap-2.5">
                <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-accent text-[var(--brand-text)]">
                  <Building2 className="size-4" />
                </div>
                <h1 className="text-xl font-semibold tracking-tight text-foreground break-words sm:text-2xl">
                  {supplier.name}
                </h1>
              </div>
              <div className="font-mono text-xs text-muted-foreground">
                {interpolate(t.common.binPrefix, { bin: supplier.bin })}
              </div>
              <SupplierBadge
                requisitesChangedDaysAgo={supplier.requisites_changed_days_ago}
                hasPendingChange={supplier.has_pending_change}
                trustedAccountsCount={supplier.trusted_accounts_count}
              />
            </div>

            <div className="text-left sm:text-right">
              <div className="text-xs text-muted-foreground">
                {t.prod.supplier.detail.totalPaid}
              </div>
              <div className="text-2xl font-bold tabular-nums whitespace-nowrap text-foreground">
                {formatMoney(supplier.total_paid_kzt)}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3 border-t border-border pt-3 text-xs sm:grid-cols-3">
            <div>
              <div className="text-muted-foreground">
                {t.prod.supplier.detail.paymentsCount}
              </div>
              <div className="mt-0.5 text-sm font-semibold tabular-nums text-foreground">
                {formatIntegerForLang(supplier.payments_count, lang)}
              </div>
            </div>
            <div>
              <div className="text-muted-foreground">
                {t.prod.supplier.detail.firstSeen}
              </div>
              <div className="mt-0.5 text-sm font-semibold text-foreground">
                {formatDate(supplier.first_seen_at)}
              </div>
            </div>
            <div>
              <div className="text-muted-foreground">
                {t.prod.supplier.detail.lastPayment}
              </div>
              <div className="mt-0.5 text-sm font-semibold text-foreground">
                {supplier.last_payment_at
                  ? formatDate(supplier.last_payment_at)
                  : "—"}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Accounts section */}
      <Card className="min-w-0 py-0">
        <CardHeader className="border-b border-border py-4">
          <CardTitle className="text-base font-semibold">
            {t.prod.supplier.detail.accountsTitle}
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {supplier.accounts.length === 0 ? (
            <div className="px-5 py-8 text-sm text-muted-foreground">
              {t.prod.supplier.detail.accountsEmpty}
            </div>
          ) : (
            <>
              {/* Mobile cards */}
              <div className="divide-y divide-border md:hidden">
                {supplier.accounts.map((acc) => (
                  <div key={acc.id} className="space-y-2.5 p-4">
                    <div className="space-y-0.5">
                      <div className="font-mono text-sm font-semibold break-all text-foreground">
                        {acc.iik}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        <span className="font-mono">{acc.bik}</span>
                        {acc.bank_name ? ` · ${acc.bank_name}` : ""}
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                      <span>
                        {interpolate(t.prod.supplier.detail.periodRange, {
                          first: formatDate(acc.first_seen_at),
                          last: formatDate(acc.last_used_at),
                        })}
                      </span>
                      <span className="tabular-nums">
                        {interpolate(t.prod.supplier.detail.paymentsCountShort, {
                          count: formatIntegerForLang(acc.payments_count, lang),
                        })}
                      </span>
                    </div>

                    <div className="flex flex-wrap items-center justify-between gap-2">
                      {acc.trusted ? (
                        <div className="space-y-1">
                          <Badge
                            variant="outline"
                            className="h-auto gap-1 border-[#00AB75]/35 bg-[#E8F8F2] py-0.5 text-[#006B49]"
                          >
                            <ShieldCheck className="size-3" />
                            <span>{t.prod.supplier.detail.trustedStatus}</span>
                          </Badge>
                          {acc.trusted_at && (
                            <div className="text-xs text-muted-foreground">
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
                        <Badge
                          variant="secondary"
                          className="h-auto py-0.5 text-xs"
                        >
                          {t.prod.supplier.detail.notTrustedStatus}
                        </Badge>
                      )}

                      {isDirector && acc.trusted && (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            setUntrustTarget(acc);
                            setUntrustComment("");
                            setUntrustError(null);
                          }}
                          className="min-h-10 gap-1.5 rounded-xl border-red-200 text-red-700 hover:bg-red-50 hover:text-red-800"
                        >
                          <ShieldOff className="size-3.5" />
                          <span>{t.prod.supplier.detail.untrustButton}</span>
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
                    <TableRow className="bg-muted/40 hover:bg-muted/40">
                      <TableHead className="pl-5">
                        {t.prod.supplier.detail.colIik}
                      </TableHead>
                      <TableHead>{t.prod.supplier.detail.colBank}</TableHead>
                      <TableHead>{t.prod.supplier.detail.colPeriod}</TableHead>
                      <TableHead className="pr-5">
                        {t.prod.supplier.detail.colTrust}
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {supplier.accounts.map((acc) => (
                      <TableRow key={acc.id}>
                        <TableCell className="pl-5 py-3.5 align-top whitespace-normal">
                          <div className="font-mono text-sm font-semibold break-all">
                            {acc.iik}
                          </div>
                          <div className="font-mono text-xs text-muted-foreground">
                            {acc.bik}
                          </div>
                        </TableCell>
                        <TableCell className="py-3.5 align-top text-sm whitespace-normal">
                          {acc.bank_name || "—"}
                        </TableCell>
                        <TableCell className="py-3.5 align-top text-xs text-muted-foreground whitespace-normal">
                          <div>
                            {interpolate(t.prod.supplier.detail.periodRange, {
                              first: formatDate(acc.first_seen_at),
                              last: formatDate(acc.last_used_at),
                            })}
                          </div>
                          <div className="mt-0.5 tabular-nums">
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
                        <TableCell className="pr-5 py-3.5 align-top whitespace-normal">
                          <div className="flex flex-wrap items-start justify-between gap-2">
                            <div className="space-y-1">
                              {acc.trusted ? (
                                <>
                                  <Badge
                                    variant="outline"
                                    className="h-auto gap-1 border-[#00AB75]/35 bg-[#E8F8F2] py-0.5 text-[#006B49]"
                                  >
                                    <ShieldCheck className="size-3" />
                                    <span>
                                      {t.prod.supplier.detail.trustedStatus}
                                    </span>
                                  </Badge>
                                  {acc.trusted_at && (
                                    <div className="text-xs text-muted-foreground">
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
                                <Badge
                                  variant="secondary"
                                  className="h-auto py-0.5 text-xs"
                                >
                                  {t.prod.supplier.detail.notTrustedStatus}
                                </Badge>
                              )}
                            </div>

                            {isDirector && acc.trusted && (
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={() => {
                                  setUntrustTarget(acc);
                                  setUntrustComment("");
                                  setUntrustError(null);
                                }}
                                className="min-h-8 gap-1.5 rounded-xl border-red-200 text-red-700 hover:bg-red-50 hover:text-red-800"
                              >
                                <ShieldOff className="size-3.5" />
                                <span>
                                  {t.prod.supplier.detail.untrustButton}
                                </span>
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
        <CardHeader className="border-b border-border py-4">
          <CardTitle className="flex items-center gap-2 text-base font-semibold">
            <History className="size-4 text-muted-foreground" />
            <span>{t.prod.supplier.detail.changesTitle}</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {supplier.changes.length === 0 ? (
            <div className="px-5 py-8 text-sm text-muted-foreground">
              {t.prod.supplier.detail.changesEmpty}
            </div>
          ) : (
            <div className="divide-y divide-border">
              {supplier.changes.map((change) => (
                <div
                  key={change.id}
                  className="flex flex-col gap-2 px-4 py-3.5 sm:px-5"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge
                        variant="outline"
                        className="h-auto border-amber-300/90 bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-950"
                      >
                        {t.prod.supplier.changeKinds[change.kind]}
                      </Badge>
                      <span className="text-xs text-muted-foreground">
                        {formatDate(change.occurred_at)}
                      </span>
                    </div>

                    {change.payment_id && (
                      <Link
                        href={`/payments/${change.payment_id}`}
                        className="inline-flex items-center gap-1 text-xs font-medium text-[var(--brand-text)] hover:underline"
                      >
                        <span>{t.prod.supplier.detail.openPayment}</span>
                        <ArrowUpRight className="size-3.5" />
                      </Link>
                    )}
                  </div>

                  <div className="flex flex-col gap-1.5 rounded-xl border border-border bg-background/80 p-3 text-xs sm:flex-row sm:items-center sm:gap-3">
                    {change.old_value && (
                      <>
                        <div className="min-w-0 flex-1 space-y-0.5">
                          <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
                            {t.prod.supplier.detail.wasLabel}
                          </div>
                          <div className="font-mono text-foreground break-all">
                            {change.old_value}
                          </div>
                        </div>
                        <ArrowRight className="size-4 shrink-0 rotate-90 text-muted-foreground sm:rotate-0" />
                      </>
                    )}
                    <div className="min-w-0 flex-1 space-y-0.5">
                      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
                        {t.prod.supplier.detail.becameLabel}
                      </div>
                      <div className="font-mono font-semibold text-foreground break-all">
                        {change.new_value}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Recent payments */}
      <Card className="min-w-0 py-0">
        <CardHeader className="border-b border-border py-4">
          <CardTitle className="text-base font-semibold">
            {t.prod.supplier.detail.paymentsTitle}
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {supplier.payments.length === 0 ? (
            <div className="px-5 py-8 text-sm text-muted-foreground">
              {t.prod.supplier.detail.paymentsEmpty}
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
              <Alert
                variant="destructive"
                className="border-red-300 bg-red-50/90"
              >
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
                  <span className="ml-1 font-semibold text-red-600">*</span>
                </Label>
                <span
                  className={cn(
                    "text-xs font-medium tabular-nums",
                    untrustTooShort ? "text-red-700" : "text-[#006B49]"
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
              className="min-h-11 w-full sm:min-h-10 sm:w-auto"
            >
              {t.common.cancel}
            </Button>
            <Button
              type="button"
              variant="destructive"
              disabled={untrustTooShort || isUntrusting}
              onClick={() => void handleUntrustSubmit()}
              className="min-h-11 w-full gap-2 sm:min-h-10 sm:w-auto"
            >
              {isUntrusting ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  <span>{t.prod.supplier.detail.untrusting}</span>
                </>
              ) : (
                <>
                  <ShieldOff className="size-4" />
                  <span>{t.prod.supplier.detail.untrustConfirm}</span>
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
