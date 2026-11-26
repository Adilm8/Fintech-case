"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { AnalystDetailsCard } from "@/components/AnalystDetailsCard";
import { ComparisonTable } from "@/components/ComparisonTable";
import { ReasonsList } from "@/components/ReasonsList";
import { VerdictBadge } from "@/components/VerdictBadge";
import { VerdictBanner } from "@/components/VerdictBanner";
import { DecisionDialog } from "@/components/prod/DecisionDialog";
import { ApprovalStatusBadge } from "@/components/prod/StatusBadge";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { useT } from "@/i18n";
import { extractInvalidFieldMap, pickHeadline } from "@/lib/format";
import {
  ApiError,
  getProdErrorMessage,
  signPayment,
} from "@/lib/prod/api";
import type { Approval, ApprovalDecision, Role } from "@/lib/prod/types";
import { notify } from "@/lib/toast";
import { cn } from "cn";

interface ApprovalsListProps {
  approvals: Approval[];
  role: Role;
  onRefresh: () => void;
}

export function ApprovalsList({
  approvals,
  role,
  onRefresh,
}: ApprovalsListProps) {
  const router = useRouter();
  const { t, lang, formatMoney, formatDate, interpolate } = useT();

  const isDirector = role === "director";
  const pendingApprovals = approvals.filter((a) => a.status === "pending");
  const resolvedApprovals = approvals.filter((a) => a.status !== "pending");

  const [activeDecision, setActiveDecision] = useState<{
    approval: Approval;
    decision: ApprovalDecision;
  } | null>(null);
  const [signingPaymentId, setSigningPaymentId] = useState<string | null>(null);
  const [signedPaymentIds, setSignedPaymentIds] = useState<Set<string>>(
    () => new Set()
  );

  const handleSignApproved = async (paymentId: string) => {
    if (!isDirector || signingPaymentId) return;
    setSigningPaymentId(paymentId);
    try {
      await signPayment(paymentId, {}, lang);
      setSignedPaymentIds((prev) => {
        const next = new Set(prev);
        next.add(paymentId);
        return next;
      });
      notify.success(t.prod.detail.toastSigned);
      onRefresh();
    } catch (err) {
      if (err instanceof ApiError && err.code === "already_signed") {
        setSignedPaymentIds((prev) => {
          const next = new Set(prev);
          next.add(paymentId);
          return next;
        });
        notify.info(t.prod.detail.blockCodes.already_signed);
      } else if (err instanceof ApiError && err.code === "verdict_changed") {
        notify.warning(t.prod.detail.verdictChangedToast, err.detail);
        router.push(`/payments/${paymentId}`);
      } else {
        notify.error(t.check.actionErrorTitle, getProdErrorMessage(err));
      }
    } finally {
      setSigningPaymentId(null);
    }
  };

  return (
    <div className="space-y-5">
      {pendingApprovals.length > 0 && (
        <div className="space-y-4">
          {pendingApprovals.map((approval) => {
            const isBudget =
              approval.check.verdict === "green" &&
              approval.check.signals.some(
                (s) => s.rule_id === "budget_payment"
              );

            return (
              <Card key={approval.id} className="min-w-0">
                <CardHeader className="border-b border-border pb-4">
                  <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-start sm:justify-between sm:gap-4">
                    <div className="min-w-0 flex-1 space-y-1">
                      <div className="flex flex-wrap items-center gap-2.5">
                        <CardTitle className="break-words">
                          {approval.request.recipient_name}
                        </CardTitle>
                        <Link
                          href={`/payments/${approval.payment_id}`}
                          className="text-xs font-medium text-[var(--brand-text)] hover:underline"
                        >
                          {t.prod.approvals.openPayment}
                        </Link>
                      </div>

                      <CardDescription className="space-y-1">
                        <div className="flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5 font-mono text-xs tabular-nums">
                          <span>
                            {interpolate(t.common.binPrefix, {
                              bin: approval.request.recipient_bin,
                            })}
                          </span>
                          <span aria-hidden="true">·</span>
                          <span className="break-all">
                            {approval.request.recipient_iik}
                          </span>
                        </div>
                        {approval.request.purpose && (
                          <div className="text-sm text-[var(--text-secondary)] break-words">
                            {approval.request.purpose}
                          </div>
                        )}
                        <div className="text-xs text-muted-foreground tabular-nums">
                          {interpolate(t.prod.approvals.sentBy, {
                            user: approval.created_by.full_name,
                          })}{" "}
                          · {formatDate(approval.created_at)}
                        </div>
                      </CardDescription>
                    </div>

                    <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 sm:flex-col sm:items-end sm:text-right sm:space-y-1">
                      <div className="text-[22px] leading-7 font-semibold tabular-nums whitespace-nowrap text-foreground">
                        {formatMoney(approval.request.amount_kzt)}
                      </div>
                      <VerdictBadge
                        verdict={approval.check.verdict}
                        label={
                          isBudget ? t.signalRules.budget_payment : undefined
                        }
                      />
                    </div>
                  </div>
                </CardHeader>

                <CardContent className="space-y-4">
                  <VerdictBanner
                    verdict={approval.check.verdict}
                    headline={pickHeadline(approval.check, lang)}
                  />

                  <ComparisonTable
                    comparison={approval.check.comparison}
                    trusted={Boolean(approval.check.trusted)}
                    invalidFields={extractInvalidFieldMap(
                      approval.check.verdict,
                      approval.check.signals
                    )}
                  />

                  <ReasonsList
                    signals={approval.check.signals}
                    score={approval.check.score}
                  />

                  {approval.check.analyst_details && (
                    <AnalystDetailsCard
                      details={approval.check.analyst_details}
                    />
                  )}

                  <div className="ui-subpanel space-y-1">
                    <div className="ui-label-meta">
                      {t.director.accountantNoteTitle}
                    </div>
                    <p className="text-sm text-foreground break-words">
                      {approval.accountant_note?.trim()
                        ? approval.accountant_note
                        : t.director.noAccountantNote}
                    </p>
                  </div>

                  {isDirector && (
                    <>
                      <Separator />
                      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
                        <Button
                          type="button"
                          disabled={approval.check.verdict === "invalid"}
                          onClick={() =>
                            setActiveDecision({
                              approval,
                              decision: "approved",
                            })
                          }
                          className="min-h-11 w-full sm:min-h-9 sm:w-auto"
                        >
                          {t.director.approve}
                        </Button>

                        <Button
                          type="button"
                          variant="destructive"
                          onClick={() =>
                            setActiveDecision({
                              approval,
                              decision: "rejected",
                            })
                          }
                          className="min-h-11 w-full sm:min-h-9 sm:w-auto"
                        >
                          {t.director.reject}
                        </Button>
                      </div>
                    </>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {resolvedApprovals.length > 0 && (
        <Card className="min-w-0 py-0">
          <CardHeader className="border-b border-border py-3.5">
            <CardTitle>{t.director.resolvedTitle}</CardTitle>
          </CardHeader>
          <CardContent className="divide-y divide-border p-0">
            {resolvedApprovals.map((approval) => {
              const isApproved = approval.status === "approved";
              const alreadySigned = signedPaymentIds.has(approval.payment_id);

              return (
                <div key={approval.id} className="space-y-3 px-4 py-3">
                  <div className="flex flex-col gap-2.5 text-sm sm:flex-row sm:flex-wrap sm:items-center sm:justify-between sm:gap-4">
                    <div className="min-w-0 space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <Link
                          href={`/payments/${approval.payment_id}`}
                          className="font-medium text-foreground hover:text-[var(--brand-text)] hover:underline break-words"
                        >
                          {approval.request.recipient_name}
                        </Link>
                        <span className="font-semibold tabular-nums whitespace-nowrap text-foreground">
                          {formatMoney(approval.request.amount_kzt)}
                        </span>
                      </div>
                      {approval.director_comment && (
                        <p className="text-xs text-muted-foreground break-words">
                          {interpolate(t.check.directorCommentLine, {
                            comment: approval.director_comment,
                          })}
                        </p>
                      )}
                      {approval.decided_by && (
                        <p className="text-xs text-muted-foreground tabular-nums">
                          {interpolate(t.prod.approvals.decidedBy, {
                            user: approval.decided_by.full_name,
                          })}
                          {approval.decided_at
                            ? ` · ${formatDate(approval.decided_at)}`
                            : ""}
                        </p>
                      )}
                    </div>

                    <div className="flex flex-wrap items-center gap-2.5">
                      {approval.trust_account && (
                        <span className="ui-tag">{t.director.trustedBadge}</span>
                      )}

                      <ApprovalStatusBadge status={approval.status} />

                      {isDirector && isApproved && !alreadySigned && (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          disabled={signingPaymentId !== null}
                          onClick={() =>
                            void handleSignApproved(approval.payment_id)
                          }
                          className="min-h-10 sm:min-h-8"
                        >
                          {signingPaymentId === approval.payment_id ? (
                            <>
                              <Loader2 className="size-3.5 animate-spin" />
                              <span>{t.prod.approvals.signingApproved}</span>
                            </>
                          ) : (
                            <span>{t.prod.approvals.signApprovedButton}</span>
                          )}
                        </Button>
                      )}

                      {alreadySigned && (
                        <span className="ui-status text-[var(--status-ok-text)]">
                          <span
                            aria-hidden="true"
                            className="ui-status-dot ui-dot-ok"
                          />
                          <span>{t.prod.approvals.signedBadge}</span>
                        </span>
                      )}

                      <Link
                        href={`/payments/${approval.payment_id}`}
                        className={cn(
                          buttonVariants({ variant: "outline", size: "sm" }),
                          "min-h-10 sm:min-h-8"
                        )}
                      >
                        {t.prod.approvals.openPayment}
                      </Link>
                    </div>
                  </div>

                  {approval.check.analyst_details && (
                    <AnalystDetailsCard
                      details={approval.check.analyst_details}
                    />
                  )}
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}

      {activeDecision && (
        <DecisionDialog
          key={`${activeDecision.approval.id}-${activeDecision.decision}`}
          open={true}
          onOpenChange={(nextOpen) => {
            if (!nextOpen) setActiveDecision(null);
          }}
          approvalId={activeDecision.approval.id}
          check={activeDecision.approval.check}
          canTrust={activeDecision.approval.can_trust}
          recipientName={activeDecision.approval.request.recipient_name}
          amountDisplay={formatMoney(
            activeDecision.approval.request.amount_kzt
          )}
          initialDecision={activeDecision.decision}
          onDecided={() => {
            setActiveDecision(null);
            onRefresh();
          }}
          onConflict={() => {
            setActiveDecision(null);
            onRefresh();
          }}
        />
      )}
    </div>
  );
}
