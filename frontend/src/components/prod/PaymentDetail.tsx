"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowLeft, Loader2 } from "lucide-react";
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
    <div className="space-y-4">
      {/* Top navigation & utility links */}
      <div className="flex flex-wrap items-center justify-between gap-2.5 sm:gap-3">
        <Link
          href="/payments"
          className={cn(
            buttonVariants({ variant: "ghost", size: "sm" }),
            "min-h-11 gap-1.5 text-muted-foreground hover:text-foreground sm:min-h-8"
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
                "min-h-10 sm:min-h-8"
              )}
            >
              {t.prod.detail.openSupplier}
            </Link>
          )}

          {canViewAudit && (
            <Link
              href={`/audit?payment_id=${encodeURIComponent(payment.id)}`}
              className={cn(
                buttonVariants({ variant: "outline", size: "sm" }),
                "min-h-10 sm:min-h-8"
              )}
            >
              {t.prod.detail.openAudit}
            </Link>
          )}

          {permissions.can_edit && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void handleRecheck()}
              disabled={isRechecking}
              className="min-h-10 sm:min-h-8"
            >
              {isRechecking && <Loader2 className="size-3.5 animate-spin" />}
              <span>
                {isRechecking ? t.check.rechecking : t.check.recheck}
              </span>
            </Button>
          )}
        </div>
      </div>

      {/* Payment summary header */}
      <div className="ui-panel min-w-0 p-4">
        <div className="flex flex-col gap-4 sm:flex-row sm:flex-wrap sm:items-start sm:justify-between">
          <div className="min-w-0 flex-1 space-y-2">
            <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
              <span className="ui-label-meta tabular-nums">
                {payment.doc_number
                  ? interpolate(t.prod.detail.docMeta, {
                      num: payment.doc_number,
                    })
                  : t.check.paymentOrderEyebrow}
                {payment.doc_date ? ` · ${formatDate(payment.doc_date)}` : ""}
              </span>
              <StatusBadge status={payment.status} />
              <span className="ui-tag">{t.prod.sources[payment.source]}</span>
            </div>

            <h1 className="ui-page-title break-words">
              {request.recipient_name}
            </h1>

            <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 font-mono text-xs text-muted-foreground tabular-nums">
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

            <div className="text-sm text-[var(--text-secondary)] break-words">
              {request.purpose}
            </div>

            <SupplierBadge
              requisitesChangedDaysAgo={supplier.requisites_changed_days_ago}
              hasPendingChange={hasPendingAccount}
              isNewSupplier={!supplier.known}
            />

            {showSecondaryTrustedNote && (
              <div className="text-xs text-muted-foreground break-words">
                <span className="ui-tag">
                  {formatTrustedBanner(check.trusted_info)}
                </span>
              </div>
            )}

            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 pt-0.5 text-xs text-muted-foreground tabular-nums">
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
            <div className="text-[22px] leading-7 font-semibold tabular-nums whitespace-nowrap text-foreground sm:text-2xl sm:leading-[30px]">
              {formatMoney(request.amount_kzt)}
            </div>
            <div className="space-y-1 text-xs text-muted-foreground tabular-nums">
              <div>
                {(check.history?.payments_count ?? 0) > 0
                  ? interpolate(t.check.historySummary, {
                      count: check.history.payments_count,
                      date: formatDate(check.history.last_payment_date),
                    })
                  : t.check.noPriorPayments}
              </div>
              {check.history?.compared_with && (
                <div>
                  <span className="ui-tag break-words">
                    {interpolate(t.check.comparedWith, {
                      supplier: check.history.compared_with,
                    })}
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Possible duplicate warning */}
      {payment.duplicate_of && (
        <div role="alert" className="ui-notice ui-notice-warn space-y-1">
          <div className="text-sm font-medium text-foreground">
            {t.prod.detail.duplicateAlertTitle}
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
            <span>{t.prod.detail.duplicateAlertDescription}</span>
            <Link
              href={`/payments/${payment.duplicate_of}`}
              className="font-medium text-[var(--brand-text)] hover:underline"
            >
              {t.prod.detail.openOriginalPayment}
            </Link>
          </div>
        </div>
      )}

      {/* Verdict changed during sign */}
      {verdictChangedDetail && (
        <div role="alert" className="ui-notice ui-notice-warn space-y-1">
          <div className="text-sm font-medium text-foreground">
            {t.prod.detail.verdictChangedTitle}
          </div>
          <p className="text-xs text-foreground break-words">
            {verdictChangedDetail}
          </p>
          <p className="text-xs text-muted-foreground">
            {t.prod.detail.verdictChangedDescription}
          </p>
        </div>
      )}

      {/* Verdict banner */}
      <VerdictBanner
        verdict={check.verdict}
        headline={pickHeadline(check, lang)}
      />

      {showProminentTrustedBanner && (
        <div role="status" className="ui-notice ui-notice-ok space-y-0.5">
          <div className="text-sm font-medium text-foreground">
            {t.check.trustedBannerTitle}
          </div>
          <p className="text-xs text-muted-foreground break-words">
            {formatTrustedBanner(check.trusted_info)}
          </p>
        </div>
      )}

      {/* Approval details block */}
      {approval && (
        <Card className="min-w-0">
          <CardHeader className="border-b border-border pb-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <CardTitle>{t.prod.detail.approvalCardTitle}</CardTitle>
              <div className="flex flex-wrap items-center gap-2">
                {approval.trust_account && (
                  <span className="ui-tag">{t.director.trustedBadge}</span>
                )}
                <ApprovalStatusBadge status={approval.status} />
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="space-y-1">
              <div className="ui-label-meta tabular-nums">
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
              <div className="ui-subpanel space-y-1">
                <div className="ui-label-meta tabular-nums">
                  {interpolate(t.prod.detail.decidedByLine, {
                    user: approval.decided_by.full_name,
                    date: formatDate(approval.decided_at),
                  })}
                </div>
                {approval.director_comment && (
                  <p className="text-sm text-foreground break-words">
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
      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-[minmax(0,1fr)_340px] xl:grid-cols-[minmax(0,1fr)_370px]">
        <div className="min-w-0 space-y-4">
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
            <div className="text-right font-mono text-[11px] text-muted-foreground">
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
