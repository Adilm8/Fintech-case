"use client";

import { useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowLeft,
  Building2,
  Copy,
  MessageSquare,
  RefreshCw,
  ScrollText,
  ShieldCheck,
} from "lucide-react";
import { AdviceBox } from "@/components/AdviceBox";
import { AnalystDetailsCard } from "@/components/AnalystDetailsCard";
import { ComparisonTable } from "@/components/ComparisonTable";
import { ReasonsList } from "@/components/ReasonsList";
import { VerdictBanner } from "@/components/VerdictBanner";
import { DecisionDialog } from "@/components/prod/DecisionDialog";
import { PaymentForm } from "@/components/prod/PaymentForm";
import { SignPanel } from "@/components/prod/SignPanel";
import {
  ApprovalStatusBadge,
  StatusBadge,
} from "@/components/prod/StatusBadge";
import { SupplierBadge } from "@/components/prod/SupplierBadge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useT } from "@/i18n";
import {
  extractInvalidFieldMap,
  pickActionText,
  pickHeadline,
} from "@/lib/format";
import {
  getApprovals,
  getProdErrorMessage,
  recheckPayment,
} from "@/lib/prod/api";
import { useSession } from "@/lib/prod/session";
import type { Payment } from "@/lib/prod/types";
import { notify } from "@/lib/toast";
import { cn } from "cn";

interface PaymentDetailProps {
  payment: Payment;
  onPaymentUpdated: (payment: Payment) => void;
  onReloadPayment: () => Promise<void>;
}

export function PaymentDetail({
  payment,
  onPaymentUpdated,
  onReloadPayment,
}: PaymentDetailProps) {
  const { t, lang, formatMoney, formatDate, interpolate, formatTrustedBanner } =
    useT();
  const { session } = useSession();

  const [isRechecking, setIsRechecking] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [verdictChangedDetail, setVerdictChangedDetail] = useState<
    string | null
  >(null);

  const [decideOpen, setDecideOpen] = useState(false);
  const [decideCanTrust, setDecideCanTrust] = useState(false);
  const [isLoadingDecide, setIsLoadingDecide] = useState(false);

  const { request, check, approval, supplier, permissions } = payment;
  const isTrusted = check.trusted === true;
  const hasTrustedInfo = isTrusted || Boolean(check.trusted_info);
  const showProminentTrustedBanner = hasTrustedInfo && check.verdict === "green";
  const showSecondaryTrustedNote = hasTrustedInfo && check.verdict !== "green";
  const invalidFields = extractInvalidFieldMap(check.verdict, check.signals);
  const hasPendingAccount = supplier.known && !supplier.account_known;
  const canViewAudit =
    session?.user.role === "director" || session?.user.role === "analyst";

  const handleRecheck = async () => {
    if (!permissions.can_edit || isRechecking) return;
    setIsRechecking(true);
    setVerdictChangedDetail(null);
    try {
      const updated = await recheckPayment(payment.id, lang);
      onPaymentUpdated(updated);
      notify.success(t.prod.detail.toastRechecked);
    } catch (err) {
      notify.error(t.check.actionErrorTitle, getProdErrorMessage(err));
    } finally {
      setIsRechecking(false);
    }
  };

  const handleOpenDecide = async () => {
    if (!approval || !permissions.can_decide || isLoadingDecide) return;
    setIsLoadingDecide(true);
    try {
      const pending = await getApprovals({ status: "pending" }, lang);
      const match = pending.find((a) => a.id === approval.id);
      setDecideCanTrust(Boolean(match?.can_trust));
      setDecideOpen(true);
    } catch (err) {
      notify.error(t.check.actionErrorTitle, getProdErrorMessage(err));
    } finally {
      setIsLoadingDecide(false);
    }
  };

  return (
    <div className="space-y-5">
      {/* Top navigation & utility links */}
      <div className="flex flex-wrap items-center justify-between gap-2.5 sm:gap-3">
        <Link
          href="/payments"
          className={cn(
            buttonVariants({ variant: "ghost", size: "sm" }),
            "min-h-11 gap-1.5 text-muted-foreground hover:text-foreground sm:min-h-9"
          )}
        >
          <ArrowLeft className="size-4" />
          <span>{t.prod.detail.backToPayments}</span>
        </Link>

        <div className="flex flex-wrap items-center gap-2">
          {supplier.id !== null && (
            <Link
              href={`/suppliers/${supplier.id}`}
              className={cn(
                buttonVariants({ variant: "outline", size: "sm" }),
                "min-h-10 gap-1.5 rounded-xl sm:min-h-9"
              )}
            >
              <Building2 className="size-3.5" />
              <span>{t.prod.detail.openSupplier}</span>
            </Link>
          )}

          {canViewAudit && (
            <Link
              href={`/audit?payment_id=${encodeURIComponent(payment.id)}`}
              className={cn(
                buttonVariants({ variant: "outline", size: "sm" }),
                "min-h-10 gap-1.5 rounded-xl sm:min-h-9"
              )}
            >
              <ScrollText className="size-3.5" />
              <span>{t.prod.detail.openAudit}</span>
            </Link>
          )}

          {permissions.can_edit && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void handleRecheck()}
              disabled={isRechecking}
              className="min-h-10 gap-1.5 rounded-xl sm:min-h-9"
            >
              <RefreshCw
                className={cn("size-3.5", isRechecking && "animate-spin")}
              />
              <span>
                {isRechecking ? t.check.rechecking : t.check.recheck}
              </span>
            </Button>
          )}
        </div>
      </div>

      {/* Payment summary card */}
      <Card className="min-w-0">
        <CardContent className="flex flex-col gap-4 py-4 sm:flex-row sm:flex-wrap sm:items-start sm:justify-between">
          <div className="min-w-0 flex-1 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                {payment.doc_number
                  ? interpolate(t.prod.detail.docMeta, {
                      num: payment.doc_number,
                    })
                  : t.check.paymentOrderEyebrow}
              </span>
              {payment.doc_date && (
                <span className="text-xs text-muted-foreground">
                  · {formatDate(payment.doc_date)}
                </span>
              )}
              <StatusBadge status={payment.status} />
              <Badge
                variant="secondary"
                className="h-auto px-2 py-0.5 text-[11px] font-medium"
              >
                {t.prod.sources[payment.source]}
              </Badge>
            </div>

            <div className="text-lg font-semibold text-foreground break-words sm:text-xl">
              {request.recipient_name}
            </div>

            <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 font-mono text-xs text-muted-foreground">
              <span>
                {interpolate(t.common.binPrefix, { bin: request.recipient_bin })}
              </span>
              <span aria-hidden="true">·</span>
              <span className="break-all">{request.recipient_iik}</span>
              <span aria-hidden="true">·</span>
              <span>{request.recipient_bik}</span>
              {(request.kbe || request.knp) && (
                <>
                  <span aria-hidden="true">·</span>
                  <span>
                    {interpolate(t.prod.detail.kbeKnpLine, {
                      kbe: request.kbe || "—",
                      knp: request.knp || "—",
                    })}
                  </span>
                </>
              )}
            </div>

            <div className="text-sm text-muted-foreground break-words">
              {request.purpose}
            </div>

            <SupplierBadge
              requisitesChangedDaysAgo={supplier.requisites_changed_days_ago}
              hasPendingChange={hasPendingAccount}
              isNewSupplier={!supplier.known}
            />

            {showSecondaryTrustedNote && (
              <div className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-muted/60 px-2.5 py-1 text-xs text-muted-foreground break-words">
                <ShieldCheck className="size-3.5 shrink-0 text-muted-foreground" />
                <span>{formatTrustedBanner(check.trusted_info)}</span>
              </div>
            )}

            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 pt-1 text-xs text-muted-foreground">
              <span>
                {interpolate(t.prod.detail.createdByLine, {
                  user: payment.created_by.full_name,
                  date: formatDate(payment.created_at),
                })}
              </span>
              {payment.signed_by && payment.signed_at && (
                <span>
                  ·{" "}
                  {interpolate(t.prod.detail.signedByLine, {
                    user: payment.signed_by.full_name,
                    date: formatDate(payment.signed_at),
                  })}
                </span>
              )}
            </div>
          </div>

          <div className="min-w-0 shrink-0 space-y-1 text-left sm:text-right">
            <div className="text-2xl font-bold tabular-nums whitespace-nowrap text-foreground sm:text-3xl">
              {formatMoney(request.amount_kzt)}
            </div>
            <div className="space-y-1 text-xs text-muted-foreground">
              <div>
                {(check.history?.payments_count ?? 0) > 0
                  ? interpolate(t.check.historySummary, {
                      count: check.history.payments_count,
                      date: formatDate(check.history.last_payment_date),
                    })
                  : t.check.noPriorPayments}
              </div>
              {check.history?.compared_with && (
                <div className="inline-block max-w-full rounded-md border border-amber-200 bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-900 break-words">
                  {interpolate(t.check.comparedWith, {
                    supplier: check.history.compared_with,
                  })}
                </div>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Possible duplicate warning */}
      {payment.duplicate_of && (
        <Alert className="rounded-xl border-amber-300 bg-amber-50/95 text-amber-950">
          <Copy className="size-4 text-amber-700" />
          <AlertTitle>{t.prod.detail.duplicateAlertTitle}</AlertTitle>
          <AlertDescription className="flex flex-wrap items-center justify-between gap-2 text-amber-900">
            <span>{t.prod.detail.duplicateAlertDescription}</span>
            <Link
              href={`/payments/${payment.duplicate_of}`}
              className="font-semibold underline underline-offset-2 hover:text-amber-950"
            >
              {t.prod.detail.openOriginalPayment}
            </Link>
          </AlertDescription>
        </Alert>
      )}

      {/* Verdict changed during sign */}
      {verdictChangedDetail && (
        <Alert
          variant="destructive"
          className="rounded-xl border-amber-400 bg-amber-50 text-amber-950"
        >
          <AlertTriangle className="size-4 text-amber-700" />
          <AlertTitle>{t.prod.detail.verdictChangedTitle}</AlertTitle>
          <AlertDescription className="space-y-1 text-amber-900 break-words">
            <p>{verdictChangedDetail}</p>
            <p className="text-xs opacity-90">
              {t.prod.detail.verdictChangedDescription}
            </p>
          </AlertDescription>
        </Alert>
      )}

      {/* Verdict banner */}
      <VerdictBanner
        verdict={check.verdict}
        headline={pickHeadline(check, lang)}
      />

      {showProminentTrustedBanner && (
        <Alert className="rounded-xl border-[#00AB75]/35 bg-[#E8F8F2] text-[#064A34]">
          <ShieldCheck className="size-4 text-[var(--brand-text)]" />
          <AlertTitle>{t.check.trustedBannerTitle}</AlertTitle>
          <AlertDescription className="font-medium text-[#064A34]/90 break-words">
            {formatTrustedBanner(check.trusted_info)}
          </AlertDescription>
        </Alert>
      )}

      {/* Approval details block */}
      {approval && (
        <Card className="min-w-0">
          <CardHeader className="border-b border-border pb-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <CardTitle className="flex items-center gap-2 text-base font-semibold">
                <MessageSquare className="size-4 text-muted-foreground" />
                <span>{t.prod.detail.approvalCardTitle}</span>
              </CardTitle>
              <div className="flex flex-wrap items-center gap-1.5">
                {approval.trust_account && (
                  <Badge
                    variant="outline"
                    className="h-auto gap-1 border-[#00AB75]/35 bg-[#E8F8F2] px-2 py-0.5 text-xs text-[#006B49]"
                  >
                    <ShieldCheck className="size-3" />
                    <span>{t.director.trustedBadge}</span>
                  </Badge>
                )}
                <ApprovalStatusBadge status={approval.status} />
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-3 pt-4 text-sm">
            <div className="space-y-1">
              <div className="text-xs text-muted-foreground">
                {interpolate(t.prod.detail.sentByLine, {
                  user: approval.created_by.full_name,
                  date: formatDate(approval.created_at),
                })}
              </div>
              <p className="text-foreground break-words">
                {approval.accountant_note?.trim()
                  ? approval.accountant_note
                  : t.director.noAccountantNote}
              </p>
            </div>

            {approval.decided_by && approval.decided_at && (
              <div className="rounded-xl border border-border bg-background/80 p-3 space-y-1">
                <div className="text-xs font-medium text-muted-foreground">
                  {interpolate(t.prod.detail.decidedByLine, {
                    user: approval.decided_by.full_name,
                    date: formatDate(approval.decided_at),
                  })}
                </div>
                {approval.director_comment && (
                  <p className="text-foreground break-words">
                    {approval.director_comment}
                  </p>
                )}
              </div>
            )}

            {approval.status === "superseded" && (
              <p className="text-xs text-muted-foreground">
                {t.prod.detail.supersededNote}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {/* Main two-column breakdown + sign panel */}
      <div className="grid grid-cols-1 items-start gap-5 lg:grid-cols-[minmax(0,1fr)_340px] xl:grid-cols-[minmax(0,1fr)_370px]">
        <div className="min-w-0 space-y-5">
          <ComparisonTable
            comparison={check.comparison}
            trusted={isTrusted}
            invalidFields={invalidFields}
          />

          <ReasonsList signals={check.signals} score={check.score} />

          {/* Analyst details strictly when server returns check.analyst_details */}
          {check.analyst_details && (
            <AnalystDetailsCard details={check.analyst_details} />
          )}

          {check.ruleset_version && (
            <div className="text-right font-mono text-[11px] text-muted-foreground/75">
              {interpolate(t.check.rulesetVersion, {
                version: check.ruleset_version,
              })}
            </div>
          )}
        </div>

        <div className="min-w-0 space-y-4 lg:sticky lg:top-28">
          <AdviceBox
            text={pickActionText(check.next_action, lang)}
            verdict={check.verdict}
          />

          <SignPanel
            payment={payment}
            onPaymentUpdated={(updated) => {
              setVerdictChangedDetail(null);
              onPaymentUpdated(updated);
            }}
            onVerdictChanged={(updated, detail) => {
              setVerdictChangedDetail(detail);
              onPaymentUpdated(updated);
            }}
            onReloadPayment={onReloadPayment}
            onOpenEdit={() => setEditOpen(true)}
            onOpenDecide={
              permissions.can_decide
                ? () => void handleOpenDecide()
                : undefined
            }
          />
        </div>
      </div>

      {/* Edit requisites dialog */}
      {permissions.can_edit && (
        <PaymentForm
          key={`edit-${payment.id}-${payment.updated_at}`}
          open={editOpen}
          onOpenChange={setEditOpen}
          mode="edit"
          payment={payment}
          onSaved={(updated) => {
            setVerdictChangedDetail(null);
            onPaymentUpdated(updated);
          }}
        />
      )}

      {/* Director decision dialog when viewing pending payment directly */}
      {permissions.can_decide && approval && (
        <DecisionDialog
          key={`decide-${approval.id}-${decideOpen ? "open" : "closed"}`}
          open={decideOpen}
          onOpenChange={setDecideOpen}
          approvalId={approval.id}
          check={check}
          canTrust={decideCanTrust}
          recipientName={request.recipient_name}
          amountDisplay={formatMoney(request.amount_kzt)}
          initialDecision="approved"
          allowDecisionSwitch
          onDecided={() => {
            void onReloadPayment();
          }}
          onConflict={() => {
            void onReloadPayment();
          }}
        />
      )}
    </div>
  );
}
