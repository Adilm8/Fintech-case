"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Loader2 } from "lucide-react";
import { AnalystDetailsCard } from "@/components/AnalystDetailsCard";
import { ComparisonTable } from "@/components/ComparisonTable";
import { ReasonsList } from "@/components/ReasonsList";
import { VerdictBadge } from "@/components/VerdictBadge";
import { VerdictBanner } from "@/components/VerdictBanner";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useT } from "@/i18n";
import {
  ApiError,
  decideApproval,
  getErrorMessage,
  getFieldErrors,
  isNetworkUnreachableError,
} from "@/lib/api";
import {
  canTrustApproval,
  MIN_DIRECTOR_COMMENT_LENGTH,
} from "@/lib/approvals";
import {
  extractInvalidFieldMap,
  parseKztString,
  pickHeadline,
} from "@/lib/format";
import { notify } from "@/lib/toast";
import type { Approval, ApprovalDecision } from "@/lib/types";
import { cn } from "cn";

interface DirectorScreenProps {
  approvals: Approval[];
  isLoading: boolean;
  analystMode: boolean;
  onAnalystModeChange: (enabled: boolean) => void;
  onRefresh: () => Promise<void> | void;
  onNetworkError: (message: string) => void;
}

function getFieldFromComparison(approval: Approval, field: string): string {
  const row = approval.check.comparison.find((c) => c.field === field);
  return row?.in_invoice ?? "";
}

function getApprovalSummary(
  approval: Approval,
  formatMoney: (amount: number | null | undefined) => string,
  recipientFallback: string
) {
  const recipientName =
    approval.request?.recipient_name ||
    getFieldFromComparison(approval, "name") ||
    recipientFallback;
  const recipientBin =
    approval.request?.recipient_bin || getFieldFromComparison(approval, "bin");
  const recipientIik =
    approval.request?.recipient_iik || getFieldFromComparison(approval, "iik");
  const purpose = approval.request?.purpose || "";

  let amountDisplay = "—";
  if (approval.request?.amount_kzt !== undefined) {
    amountDisplay = formatMoney(approval.request.amount_kzt);
  } else {
    const rawAmount = getFieldFromComparison(approval, "amount");
    if (rawAmount) {
      const parsed = parseKztString(rawAmount);
      amountDisplay = parsed !== null ? formatMoney(parsed) : rawAmount;
    }
  }

  return {
    recipientName,
    recipientBin,
    recipientIik,
    purpose,
    amountDisplay,
  };
}

interface PendingApprovalCardProps {
  approval: Approval;
  analystMode: boolean;
  onDecided: (decision: ApprovalDecision, recipientName: string) => Promise<void>;
  onConflictError: (message: string) => Promise<void>;
  onNetworkError: (message: string) => void;
}

function PendingApprovalCard({
  approval,
  analystMode,
  onDecided,
  onConflictError,
  onNetworkError,
}: PendingApprovalCardProps) {
  const { t, lang, formatMoney, interpolate, plural } = useT();
  const [comment, setComment] = useState("");
  const [trustAccount, setTrustAccount] = useState(false);
  const [submittingDecision, setSubmittingDecision] =
    useState<ApprovalDecision | null>(null);
  const [cardError, setCardError] = useState<string | null>(null);
  const [commentFieldError, setCommentFieldError] = useState<string | null>(
    null
  );
  const [rejectDialogOpen, setRejectDialogOpen] = useState(false);

  const summary = getApprovalSummary(
    approval,
    formatMoney,
    t.director.recipientFallback
  );
  const isRed = approval.check.verdict === "red";
  const isBudgetPayment =
    approval.check.verdict === "green" &&
    approval.check.signals.some((s) => s.rule_id === "budget_payment");
  const allowTrust = canTrustApproval(approval);
  const effectiveTrust = allowTrust && trustAccount;
  const trimmedComment = comment.trim();
  const commentRequiredForApprove = isRed || effectiveTrust;
  const commentTooShort =
    commentRequiredForApprove &&
    trimmedComment.length < MIN_DIRECTOR_COMMENT_LENGTH;

  const isApproveDisabled = submittingDecision !== null || commentTooShort;
  const minCharsLabel = plural(
    MIN_DIRECTOR_COMMENT_LENGTH,
    t.plurals.charsGenitive
  );

  const handleDecision = async (decision: ApprovalDecision) => {
    setCardError(null);
    setCommentFieldError(null);
    setSubmittingDecision(decision);
    try {
      await decideApproval(
        approval.id,
        {
          decision,
          director_comment: trimmedComment,
          trust_account: decision === "approved" ? effectiveTrust : false,
        },
        lang,
        { analyst: analystMode }
      );
      setRejectDialogOpen(false);
      await onDecided(decision, summary.recipientName);
    } catch (err) {
      const message = getErrorMessage(err);
      const fieldErrors = getFieldErrors(err);
      if (isNetworkUnreachableError(err)) {
        setRejectDialogOpen(false);
        onNetworkError(message);
        notify.error(t.common.serverErrorTitle, message);
      } else if (err instanceof ApiError && err.status === 409) {
        setRejectDialogOpen(false);
        await onConflictError(message);
      } else {
        setRejectDialogOpen(false);
        if (fieldErrors.director_comment) {
          setCommentFieldError(fieldErrors.director_comment);
        }
        setCardError(message);
        notify.error(t.director.saveErrorTitle, message);
      }
    } finally {
      setSubmittingDecision(null);
    }
  };

  return (
    <Card className="min-w-0">
      <CardHeader className="border-b border-border pb-3.5">
        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-start sm:justify-between sm:gap-4">
          <div className="min-w-0 flex-1 space-y-1">
            <CardTitle className="text-base font-semibold break-words">
              {summary.recipientName}
            </CardTitle>
            <CardDescription className="space-y-1">
              {(summary.recipientBin || summary.recipientIik) && (
                <div className="flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5 font-mono text-xs tabular-nums">
                  {summary.recipientBin && (
                    <span>
                      {interpolate(t.common.binPrefix, {
                        bin: summary.recipientBin,
                      })}
                    </span>
                  )}
                  {summary.recipientBin && summary.recipientIik && (
                    <span aria-hidden="true">·</span>
                  )}
                  {summary.recipientIik && (
                    <span className="break-all">{summary.recipientIik}</span>
                  )}
                </div>
              )}
              {summary.purpose && (
                <div className="text-sm text-[var(--text-secondary)] break-words">
                  {summary.purpose}
                </div>
              )}
              {approval.check.history?.compared_with && (
                <div className="pt-0.5">
                  <span className="ui-tag max-w-full whitespace-normal break-words">
                    {interpolate(t.check.comparedWith, {
                      supplier: approval.check.history.compared_with,
                    })}
                  </span>
                </div>
              )}
            </CardDescription>
          </div>
          <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 sm:flex-col sm:items-end sm:space-y-1 sm:text-right">
            <div className="text-[22px] leading-7 font-semibold tabular-nums whitespace-nowrap text-foreground">
              {summary.amountDisplay}
            </div>
            <VerdictBadge
              verdict={approval.check.verdict}
              label={
                isBudgetPayment ? t.signalRules.budget_payment : undefined
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

        {analystMode && (
          <AnalystDetailsCard details={approval.check.analyst_details} />
        )}

        <div className="ui-subpanel space-y-1">
          <div className="ui-label-meta">{t.director.accountantNoteTitle}</div>
          <p className="text-sm text-foreground break-words">
            {approval.accountant_note?.trim()
              ? approval.accountant_note
              : t.director.noAccountantNote}
          </p>
        </div>

        <Separator />

        <div className="space-y-3.5">
          {cardError && (
            <div
              role="alert"
              className="ui-notice ui-notice-danger space-y-0.5"
            >
              <div className="text-[13px] font-semibold text-[var(--status-danger-text)]">
                {t.director.saveErrorTitle}
              </div>
              <p className="text-xs text-foreground break-words">{cardError}</p>
            </div>
          )}

          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Label htmlFor={`director-comment-${approval.id}`}>
                {t.director.directorCommentLabel}
                {commentRequiredForApprove && (
                  <span className="ml-1 font-semibold text-[var(--status-danger-text)]">
                    *
                  </span>
                )}
              </Label>
              {commentRequiredForApprove && (
                <span
                  className={cn(
                    "text-xs font-medium tabular-nums",
                    commentTooShort
                      ? "text-[var(--status-danger-text)]"
                      : "text-[var(--status-ok-text)]"
                  )}
                >
                  {interpolate(
                    isRed
                      ? t.director.requiredForRedApprove
                      : t.director.requiredForTrustApprove,
                    {
                      minChars: minCharsLabel,
                      current: trimmedComment.length,
                      min: MIN_DIRECTOR_COMMENT_LENGTH,
                    }
                  )}
                </span>
              )}
            </div>
            <Textarea
              id={`director-comment-${approval.id}`}
              rows={3}
              aria-required={commentRequiredForApprove}
              aria-invalid={Boolean(commentFieldError)}
              className="min-h-24 w-full"
              placeholder={
                commentRequiredForApprove
                  ? interpolate(t.director.commentPlaceholderRequired, {
                      minChars: minCharsLabel,
                    })
                  : t.director.commentPlaceholderOptional
              }
              value={comment}
              onChange={(e) => {
                setComment(e.target.value);
                if (cardError) setCardError(null);
                if (commentFieldError) setCommentFieldError(null);
              }}
            />
            {commentFieldError && (
              <p className="text-xs font-medium text-[var(--status-danger-text)] break-words">
                {commentFieldError}
              </p>
            )}
            {commentRequiredForApprove && (
              <p className="text-xs text-muted-foreground">
                {t.director.rejectNoCommentHint}
              </p>
            )}
          </div>

          {allowTrust && (
            <div className="ui-subpanel flex min-h-10 items-start gap-2.5">
              <Checkbox
                id={`trust-account-${approval.id}`}
                checked={trustAccount}
                onCheckedChange={(checked) => {
                  setTrustAccount(Boolean(checked));
                  if (cardError) setCardError(null);
                }}
                className="mt-0.5"
              />
              <div className="min-w-0 flex-1 space-y-0.5">
                <Label
                  htmlFor={`trust-account-${approval.id}`}
                  className="cursor-pointer font-medium text-foreground"
                >
                  {t.director.trustAccountLabel}
                </Label>
                <p className="text-xs text-muted-foreground">
                  {interpolate(t.director.trustAccountDescription, {
                    minChars: minCharsLabel,
                  })}
                </p>
              </div>
            </div>
          )}

          <div className="flex flex-col gap-2 pt-0.5 sm:flex-row sm:flex-wrap sm:items-center sm:gap-2.5">
            <Button
              type="button"
              disabled={isApproveDisabled}
              onClick={() => handleDecision("approved")}
              className="min-h-10 w-full sm:min-h-9 sm:w-auto"
            >
              {submittingDecision === "approved" ? (
                <>
                  <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                  <span>{t.director.saving}</span>
                </>
              ) : (
                t.director.approve
              )}
            </Button>

            <Button
              type="button"
              variant="destructive"
              disabled={submittingDecision !== null}
              onClick={() => setRejectDialogOpen(true)}
              className="min-h-10 w-full sm:min-h-9 sm:w-auto"
            >
              {submittingDecision === "rejected" ? (
                <>
                  <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                  <span>{t.director.rejecting}</span>
                </>
              ) : (
                t.director.reject
              )}
            </Button>
          </div>

          <Dialog
            open={rejectDialogOpen}
            onOpenChange={(nextOpen) => {
              if (submittingDecision === null) {
                setRejectDialogOpen(nextOpen);
              }
            }}
          >
            <DialogContent className="sm:max-w-md">
              <DialogHeader>
                <DialogTitle>{t.director.rejectConfirmTitle}</DialogTitle>
                <DialogDescription>
                  {interpolate(t.director.rejectConfirmDescription, {
                    recipient: summary.recipientName,
                    amount: summary.amountDisplay,
                  })}
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setRejectDialogOpen(false)}
                  disabled={submittingDecision !== null}
                  className="min-h-10 w-full sm:min-h-9 sm:w-auto"
                >
                  {t.common.cancel}
                </Button>
                <Button
                  type="button"
                  variant="destructive"
                  onClick={() => void handleDecision("rejected")}
                  disabled={submittingDecision !== null}
                  className="min-h-10 w-full sm:min-h-9 sm:w-auto"
                >
                  {submittingDecision === "rejected" ? (
                    <>
                      <Loader2
                        className="size-4 animate-spin"
                        aria-hidden="true"
                      />
                      <span>{t.director.rejecting}</span>
                    </>
                  ) : (
                    t.director.rejectConfirmAction
                  )}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          {approval.check.ruleset_version && (
            <div className="pt-0.5 text-right font-mono text-[11px] tabular-nums text-muted-foreground">
              {interpolate(t.check.rulesetVersion, {
                version: approval.check.ruleset_version,
              })}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export function DirectorScreen({
  approvals,
  isLoading,
  analystMode,
  onAnalystModeChange,
  onRefresh,
  onNetworkError,
}: DirectorScreenProps) {
  const { t, formatMoney, formatDate, interpolate } = useT();

  const pendingApprovals = useMemo(
    () => approvals.filter((a) => a.status === "pending"),
    [approvals]
  );
  const resolvedApprovals = useMemo(
    () => approvals.filter((a) => a.status !== "pending"),
    [approvals]
  );
  const highRiskPendingCount = useMemo(
    () =>
      pendingApprovals.filter(
        (a) => a.check.verdict === "red" || a.check.verdict === "invalid"
      ).length,
    [pendingApprovals]
  );
  const trustedCount = useMemo(
    () =>
      resolvedApprovals.filter(
        (a) => a.status === "approved" && a.trust_account
      ).length,
    [resolvedApprovals]
  );

  const handleDecided = async (
    decision: ApprovalDecision,
    recipientName: string
  ) => {
    const description = interpolate(t.toast.decisionSavedDescription, {
      recipient: recipientName,
    });
    if (decision === "approved") {
      notify.success(t.toast.approvedTitle, description);
    } else {
      notify.info(t.toast.rejectedTitle, description);
    }
    await onRefresh();
  };

  const handleConflictError = async (message: string) => {
    notify.error(t.director.conflictTitle, message);
    await onRefresh();
  };

  return (
    <div className="space-y-4 sm:space-y-5">
      <div className="ui-page-header">
        <div className="min-w-0">
          <h1 className="ui-page-title">{t.director.title}</h1>
          <p className="ui-page-subtitle">{t.director.subtitle}</p>
        </div>

        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <button
            type="button"
            role="switch"
            aria-checked={analystMode}
            onClick={() => onAnalystModeChange(!analystMode)}
            className={cn(
              "inline-flex h-10 w-full cursor-pointer items-center justify-between gap-2.5 rounded-[6px] border px-3 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:h-9 sm:w-auto sm:justify-start",
              analystMode
                ? "border-foreground bg-muted text-foreground"
                : "border-input bg-card text-muted-foreground hover:bg-muted hover:text-foreground"
            )}
          >
            <span>{t.director.analystViewToggle}</span>
            <span
              aria-hidden="true"
              className={cn(
                "relative inline-flex h-4 w-7 shrink-0 items-center rounded-full transition-colors",
                analystMode ? "bg-foreground" : "bg-muted-foreground/30"
              )}
            >
              <span
                className={cn(
                  "inline-block size-3 rounded-full bg-card transition-transform",
                  analystMode ? "translate-x-3.5" : "translate-x-0.5"
                )}
              />
            </span>
          </button>

          <Button
            type="button"
            variant="outline"
            onClick={() => void onRefresh()}
            disabled={isLoading}
            className="min-h-10 w-full sm:min-h-9 sm:w-auto"
          >
            {isLoading && (
              <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
            )}
            <span>{t.common.refresh}</span>
          </Button>
        </div>
      </div>

      {/* Summary strip */}
      <div className="ui-kpi-strip">
        {isLoading && approvals.length === 0 ? (
          Array.from({ length: 4 }).map((_, index) => (
            <div key={`approval-tile-skeleton-${index}`} className="ui-kpi-cell">
              <Skeleton className="h-3.5 w-24 rounded-[4px]" />
              <Skeleton className="h-6 w-14 rounded-[4px]" />
            </div>
          ))
        ) : (
          <>
            <div className="ui-kpi-cell">
              <span className="ui-kpi-label">
                {t.director.tiles.pendingLabel}
              </span>
              <div className="ui-kpi-value">{pendingApprovals.length}</div>
            </div>

            <div className="ui-kpi-cell">
              <span className="ui-kpi-label">
                {t.director.tiles.highRiskLabel}
              </span>
              <div
                className={cn(
                  "ui-kpi-value",
                  highRiskPendingCount > 0 && "text-[var(--status-danger-text)]"
                )}
              >
                {highRiskPendingCount}
              </div>
            </div>

            <div className="ui-kpi-cell">
              <span className="ui-kpi-label">
                {t.director.tiles.resolvedLabel}
              </span>
              <div className="ui-kpi-value">{resolvedApprovals.length}</div>
            </div>

            <div className="ui-kpi-cell">
              <span className="ui-kpi-label">
                {t.director.tiles.trustedLabel}
              </span>
              <div className="ui-kpi-value">{trustedCount}</div>
            </div>
          </>
        )}
      </div>

      {isLoading && approvals.length === 0 ? (
        <Card className="min-w-0">
          <CardHeader className="border-b border-border pb-3.5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="space-y-2">
                <Skeleton className="h-5 w-56 rounded-[4px]" />
                <Skeleton className="h-4 w-72 rounded-[4px]" />
                <Skeleton className="h-4 w-64 rounded-[4px]" />
              </div>
              <div className="flex flex-col items-start gap-2 sm:items-end">
                <Skeleton className="h-7 w-36 rounded-[4px]" />
                <Skeleton className="h-4 w-28 rounded-[4px]" />
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <Skeleton className="h-14 w-full rounded-[6px]" />
            <div className="space-y-2">
              <Skeleton className="h-10 w-full rounded-[6px]" />
              <Skeleton className="h-10 w-full rounded-[6px]" />
              <Skeleton className="h-10 w-full rounded-[6px]" />
            </div>
            <Skeleton className="h-24 w-full rounded-[6px]" />
            <div className="flex gap-2.5">
              <Skeleton className="h-9 w-32 rounded-[6px]" />
              <Skeleton className="h-9 w-32 rounded-[6px]" />
            </div>
          </CardContent>
        </Card>
      ) : pendingApprovals.length === 0 ? (
        <div className="ui-panel">
          <div className="ui-empty">
            <div className="ui-empty-title">{t.director.emptyTitle}</div>
            <p className="ui-empty-desc">{t.director.emptyDescription}</p>
            <Link
              href="/"
              className="mt-2 inline-flex min-h-10 items-center gap-1.5 rounded-[6px] border border-input bg-card px-2.5 text-xs font-medium text-foreground transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:min-h-8"
            >
              <ArrowLeft className="size-3.5" />
              <span>{t.director.backToPayments}</span>
            </Link>
          </div>
        </div>
      ) : (
        <div className="space-y-5">
          {pendingApprovals.map((approval) => (
            <PendingApprovalCard
              key={approval.id}
              approval={approval}
              analystMode={analystMode}
              onDecided={handleDecided}
              onConflictError={handleConflictError}
              onNetworkError={onNetworkError}
            />
          ))}
        </div>
      )}

      {resolvedApprovals.length > 0 && (
        <Card className="min-w-0">
          <CardHeader className="border-b border-border pb-3">
            <CardTitle>{t.director.resolvedTitle}</CardTitle>
          </CardHeader>
          <CardContent className="divide-y divide-border p-0">
            {resolvedApprovals.map((approval) => {
              const summary = getApprovalSummary(
                approval,
                formatMoney,
                t.director.recipientFallback
              );
              const isApproved = approval.status === "approved";

              return (
                <div key={approval.id} className="space-y-3 px-4 py-3">
                  <div className="flex flex-col gap-2 text-sm sm:flex-row sm:flex-wrap sm:items-center sm:justify-between sm:gap-4">
                    <div className="min-w-0 space-y-0.5">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium text-foreground break-words">
                          {summary.recipientName}
                        </span>
                        <span className="font-medium tabular-nums whitespace-nowrap text-foreground">
                          {summary.amountDisplay}
                        </span>
                      </div>
                      {approval.director_comment && (
                        <p className="text-xs text-muted-foreground break-words">
                          {interpolate(t.check.directorCommentLine, {
                            comment: approval.director_comment,
                          })}
                        </p>
                      )}
                    </div>

                    <div className="flex flex-wrap items-center gap-2.5">
                      {approval.trust_account && (
                        <span className="ui-tag">
                          {t.director.trustedBadge}
                        </span>
                      )}
                      <span
                        className={cn(
                          "ui-status",
                          isApproved
                            ? "text-[var(--status-ok-text)]"
                            : "text-[var(--status-danger-text)]"
                        )}
                      >
                        <span
                          aria-hidden="true"
                          className={cn(
                            "ui-status-dot",
                            isApproved ? "ui-dot-ok" : "ui-dot-danger"
                          )}
                        />
                        <span>
                          {isApproved
                            ? t.director.statusApprovedShort
                            : t.director.statusRejectedShort}
                        </span>
                      </span>
                      {approval.decided_at && (
                        <span className="text-xs tabular-nums text-muted-foreground">
                          {formatDate(approval.decided_at)}
                        </span>
                      )}
                    </div>
                  </div>

                  {analystMode && approval.check.analyst_details && (
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
    </div>
  );
}
