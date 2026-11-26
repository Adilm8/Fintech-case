"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ClipboardCheck,
  Inbox,
  Loader2,
  Lock,
  MessageSquare,
  RefreshCw,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { AnalystDetailsCard } from "@/components/AnalystDetailsCard";
import { ComparisonTable } from "@/components/ComparisonTable";
import { ReasonsList } from "@/components/ReasonsList";
import { VerdictBadge } from "@/components/VerdictBadge";
import { VerdictBanner } from "@/components/VerdictBanner";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
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
      <CardHeader className="border-b border-border pb-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-start sm:justify-between sm:gap-4">
          <div className="min-w-0 flex-1 space-y-1">
            <CardTitle className="text-lg font-semibold break-words">
              {summary.recipientName}
            </CardTitle>
            <CardDescription className="space-y-1">
              {(summary.recipientBin || summary.recipientIik) && (
                <div className="flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5 font-mono text-xs">
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
                <div className="text-sm text-muted-foreground break-words">
                  {summary.purpose}
                </div>
              )}
              {approval.check.history?.compared_with && (
                <div className="inline-block max-w-full rounded-md border border-amber-200 bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-900 break-words">
                  {interpolate(t.check.comparedWith, {
                    supplier: approval.check.history.compared_with,
                  })}
                </div>
              )}
            </CardDescription>
          </div>
          <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 sm:flex-col sm:items-end sm:text-right sm:space-y-1">
            <div className="text-2xl font-bold tabular-nums whitespace-nowrap text-foreground">
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

      <CardContent className="pt-5 space-y-5">
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

        <div className="rounded-xl border border-border bg-background/80 p-4 space-y-1.5">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            <MessageSquare className="size-3.5 shrink-0" />
            <span>{t.director.accountantNoteTitle}</span>
          </div>
          <p className="text-sm text-foreground break-words">
            {approval.accountant_note?.trim()
              ? approval.accountant_note
              : t.director.noAccountantNote}
          </p>
        </div>

        <Separator />

        <div className="space-y-4">
          {cardError && (
            <Alert variant="destructive" className="bg-red-50/90 border-red-300">
              <AlertCircle className="size-4" />
              <AlertTitle>{t.director.saveErrorTitle}</AlertTitle>
              <AlertDescription className="break-words">
                {cardError}
              </AlertDescription>
            </Alert>
          )}

          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Label htmlFor={`director-comment-${approval.id}`}>
                {t.director.directorCommentLabel}
                {commentRequiredForApprove && (
                  <span className="ml-1 text-red-600 font-semibold">*</span>
                )}
              </Label>
              {commentRequiredForApprove && (
                <span
                  className={cn(
                    "text-xs font-medium tabular-nums",
                    commentTooShort ? "text-red-700" : "text-[#006B49]"
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
              className={cn(
                "w-full min-h-24",
                commentFieldError &&
                  "border-rose-500 bg-rose-50/60 focus-visible:border-rose-600 focus-visible:ring-rose-500/25"
              )}
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
              <p className="text-xs font-medium text-rose-800 break-words">
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
            <div className="flex min-h-11 items-start gap-3 rounded-xl border border-border bg-background/80 px-3.5 py-2.5">
              <Checkbox
                id={`trust-account-${approval.id}`}
                checked={trustAccount}
                onCheckedChange={(checked) => {
                  setTrustAccount(Boolean(checked));
                  if (cardError) setCardError(null);
                }}
                className="mt-1"
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

          <div className="flex flex-col gap-2.5 pt-1 sm:flex-row sm:flex-wrap sm:items-center sm:gap-3">
            <Button
              type="button"
              size="lg"
              disabled={isApproveDisabled}
              onClick={() => handleDecision("approved")}
              className="min-h-11 w-full gap-2 sm:w-auto"
            >
              {submittingDecision === "approved" ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  <span>{t.director.saving}</span>
                </>
              ) : (
                <>
                  <CheckCircle2 className="size-4" />
                  <span>{t.director.approve}</span>
                </>
              )}
            </Button>

            <Button
              type="button"
              variant="destructive"
              size="lg"
              disabled={submittingDecision !== null}
              onClick={() => setRejectDialogOpen(true)}
              className="min-h-11 w-full gap-2 sm:w-auto"
            >
              {submittingDecision === "rejected" ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  <span>{t.director.rejecting}</span>
                </>
              ) : (
                <>
                  <XCircle className="size-4" />
                  <span>{t.director.reject}</span>
                </>
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
                  className="min-h-11 w-full sm:min-h-9 sm:w-auto"
                >
                  {t.common.cancel}
                </Button>
                <Button
                  type="button"
                  variant="destructive"
                  onClick={() => void handleDecision("rejected")}
                  disabled={submittingDecision !== null}
                  className="min-h-11 w-full gap-1.5 sm:min-h-9 sm:w-auto"
                >
                  {submittingDecision === "rejected" ? (
                    <>
                      <Loader2 className="size-4 animate-spin" />
                      <span>{t.director.rejecting}</span>
                    </>
                  ) : (
                    <>
                      <XCircle className="size-4" />
                      <span>{t.director.rejectConfirmAction}</span>
                    </>
                  )}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          {approval.check.ruleset_version && (
            <div className="pt-1 text-right font-mono text-[11px] text-muted-foreground/75">
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
    <div className="space-y-5 sm:space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold tracking-tight text-foreground sm:text-2xl">
            {t.director.title}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {t.director.subtitle}
          </p>
        </div>

        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-2.5">
          <button
            type="button"
            role="switch"
            aria-checked={analystMode}
            onClick={() => onAnalystModeChange(!analystMode)}
            className={cn(
              "inline-flex min-h-11 w-full items-center justify-between gap-2.5 rounded-xl border px-3 py-1.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:min-h-9 sm:w-auto sm:justify-start",
              analystMode
                ? "border-slate-400 bg-slate-100 text-slate-900"
                : "border-border bg-card text-muted-foreground hover:bg-muted/60 hover:text-foreground"
            )}
          >
            <span className="inline-flex items-center gap-1.5">
              <Lock className="size-3.5 shrink-0" />
              <span>{t.director.analystViewToggle}</span>
            </span>
            <span
              aria-hidden="true"
              className={cn(
                "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors",
                analystMode ? "bg-slate-700" : "bg-muted-foreground/30"
              )}
            >
              <span
                className={cn(
                  "inline-block size-3.5 rounded-full bg-white shadow-xs transition-transform",
                  analystMode ? "translate-x-[18px]" : "translate-x-1"
                )}
              />
            </span>
          </button>

          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => void onRefresh()}
            disabled={isLoading}
            className="min-h-11 w-full gap-1.5 rounded-xl sm:min-h-9 sm:w-auto"
          >
            <RefreshCw className={cn("size-3.5", isLoading && "animate-spin")} />
            <span>{t.common.refresh}</span>
          </Button>
        </div>
      </div>

      {/* Summary tiles */}
      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        {isLoading && approvals.length === 0 ? (
          Array.from({ length: 4 }).map((_, index) => (
            <Card key={`approval-tile-skeleton-${index}`} className="py-4">
              <CardContent className="space-y-3">
                <div className="flex items-center justify-between gap-2">
                  <Skeleton className="h-3.5 w-24" />
                  <Skeleton className="size-8 rounded-xl" />
                </div>
                <Skeleton className="h-8 w-14" />
              </CardContent>
            </Card>
          ))
        ) : (
          <>
            <Card className="py-4">
              <CardContent className="flex flex-col justify-between gap-2">
                <div className="flex items-start justify-between gap-2">
                  <span className="text-xs font-medium text-muted-foreground sm:text-sm">
                    {t.director.tiles.pendingLabel}
                  </span>
                  <div
                    className={cn(
                      "flex size-8 shrink-0 items-center justify-center rounded-xl",
                      pendingApprovals.length > 0
                        ? "bg-amber-50 text-amber-700"
                        : "bg-accent text-[var(--brand-text)]"
                    )}
                  >
                    <ClipboardCheck className="size-4" />
                  </div>
                </div>
                <div className="text-2xl font-bold tabular-nums text-foreground sm:text-3xl">
                  {pendingApprovals.length}
                </div>
              </CardContent>
            </Card>

            <Card className="py-4">
              <CardContent className="flex flex-col justify-between gap-2">
                <div className="flex items-start justify-between gap-2">
                  <span className="text-xs font-medium text-muted-foreground sm:text-sm">
                    {t.director.tiles.highRiskLabel}
                  </span>
                  <div
                    className={cn(
                      "flex size-8 shrink-0 items-center justify-center rounded-xl",
                      highRiskPendingCount > 0
                        ? "bg-red-50 text-red-600"
                        : "bg-muted text-muted-foreground"
                    )}
                  >
                    <AlertTriangle className="size-4" />
                  </div>
                </div>
                <div
                  className={cn(
                    "text-2xl font-bold tabular-nums sm:text-3xl",
                    highRiskPendingCount > 0 ? "text-red-700" : "text-foreground"
                  )}
                >
                  {highRiskPendingCount}
                </div>
              </CardContent>
            </Card>

            <Card className="py-4">
              <CardContent className="flex flex-col justify-between gap-2">
                <div className="flex items-start justify-between gap-2">
                  <span className="text-xs font-medium text-muted-foreground sm:text-sm">
                    {t.director.tiles.resolvedLabel}
                  </span>
                  <div className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-muted text-foreground/75">
                    <CheckCircle2 className="size-4" />
                  </div>
                </div>
                <div className="text-2xl font-bold tabular-nums text-foreground sm:text-3xl">
                  {resolvedApprovals.length}
                </div>
              </CardContent>
            </Card>

            <Card className="py-4">
              <CardContent className="flex flex-col justify-between gap-2">
                <div className="flex items-start justify-between gap-2">
                  <span className="text-xs font-medium text-muted-foreground sm:text-sm">
                    {t.director.tiles.trustedLabel}
                  </span>
                  <div className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-accent text-[var(--brand-text)]">
                    <ShieldCheck className="size-4" />
                  </div>
                </div>
                <div className="text-2xl font-bold tabular-nums text-foreground sm:text-3xl">
                  {trustedCount}
                </div>
              </CardContent>
            </Card>
          </>
        )}
      </div>

      {isLoading && approvals.length === 0 ? (
        <Card className="min-w-0">
          <CardHeader className="border-b border-border pb-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="space-y-2">
                <Skeleton className="h-6 w-56" />
                <Skeleton className="h-4 w-72" />
                <Skeleton className="h-4 w-64" />
              </div>
              <div className="flex flex-col items-start gap-2 sm:items-end">
                <Skeleton className="h-8 w-36" />
                <Skeleton className="h-6 w-28 rounded-full" />
              </div>
            </div>
          </CardHeader>
          <CardContent className="pt-5 space-y-5">
            <Skeleton className="h-16 w-full rounded-xl" />
            <div className="space-y-2.5">
              <Skeleton className="h-10 w-full rounded-lg" />
              <Skeleton className="h-10 w-full rounded-lg" />
              <Skeleton className="h-10 w-full rounded-lg" />
            </div>
            <Skeleton className="h-24 w-full rounded-xl" />
            <div className="flex gap-3">
              <Skeleton className="h-11 w-32 rounded-lg" />
              <Skeleton className="h-11 w-32 rounded-lg" />
            </div>
          </CardContent>
        </Card>
      ) : pendingApprovals.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center gap-3 py-14 text-center">
            <div className="flex size-12 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
              <Inbox className="size-6" />
            </div>
            <div className="space-y-1">
              <div className="text-base font-semibold text-foreground">
                {t.director.emptyTitle}
              </div>
              <p className="max-w-md text-sm text-muted-foreground">
                {t.director.emptyDescription}
              </p>
            </div>
            <Link
              href="/"
              className="mt-1 inline-flex min-h-11 items-center gap-2 rounded-xl border border-border bg-card px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:min-h-9"
            >
              <ArrowLeft className="size-4" />
              <span>{t.director.backToPayments}</span>
            </Link>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-6">
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
          <CardHeader className="border-b border-border pb-3.5">
            <CardTitle className="text-base font-semibold">
              {t.director.resolvedTitle}
            </CardTitle>
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
                <div key={approval.id} className="space-y-3 px-4 py-3.5 sm:px-5">
                  <div className="flex flex-col gap-2.5 text-sm sm:flex-row sm:flex-wrap sm:items-center sm:justify-between sm:gap-4">
                    <div className="min-w-0 space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium text-foreground break-words">
                          {summary.recipientName}
                        </span>
                        <span className="font-semibold tabular-nums whitespace-nowrap text-foreground">
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

                    <div className="flex flex-wrap items-center gap-2">
                      {approval.trust_account && (
                        <Badge
                          variant="outline"
                          className="h-auto gap-1 border-[#00AB75]/35 bg-[#E8F8F2] py-0.5 text-[#006B49]"
                        >
                          <ShieldCheck className="size-3" />
                          <span>{t.director.trustedBadge}</span>
                        </Badge>
                      )}
                      <Badge
                        variant="outline"
                        className={cn(
                          "h-auto py-0.5",
                          isApproved
                            ? "border-[#00AB75]/35 bg-[#E8F8F2] text-[#006B49]"
                            : "border-red-200 bg-red-50 text-red-800"
                        )}
                      >
                        {isApproved
                          ? t.director.statusApprovedShort
                          : t.director.statusRejectedShort}
                      </Badge>
                      {approval.decided_at && (
                        <span className="text-xs text-muted-foreground">
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
