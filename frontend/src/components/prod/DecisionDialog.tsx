"use client";

import { useState } from "react";
import { AlertCircle, Loader2 } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
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
import { Textarea } from "@/components/ui/textarea";
import { useT } from "@/i18n";
import {
  ApiError,
  decideApproval,
  getProdErrorMessage,
} from "@/lib/prod/api";
import { notifyProdApprovalsUpdated } from "@/components/prod/ProdShell";
import {
  MIN_DIRECTOR_COMMENT_LENGTH,
  type Approval,
  type ApprovalDecision,
  type CheckResult,
} from "@/lib/prod/types";
import { notify } from "@/lib/toast";
import { cn } from "cn";

interface DecisionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  approvalId: string;
  check: CheckResult;
  canTrust: boolean;
  recipientName?: string;
  amountDisplay?: string;
  initialDecision?: ApprovalDecision;
  allowDecisionSwitch?: boolean;
  onDecided: (updated: Approval) => void;
  onConflict?: () => void;
}

export function DecisionDialog({
  open,
  onOpenChange,
  approvalId,
  check,
  canTrust,
  recipientName,
  amountDisplay,
  initialDecision = "approved",
  allowDecisionSwitch = false,
  onDecided,
  onConflict,
}: DecisionDialogProps) {
  const { t, lang, interpolate, plural } = useT();

  const [decision, setDecision] = useState<ApprovalDecision>(initialDecision);
  const [comment, setComment] = useState("");
  const [trustAccount, setTrustAccount] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isApprove = decision === "approved";
  const isInvalid = check.verdict === "invalid";
  const isRed = check.verdict === "red";
  const effectiveTrust = isApprove && canTrust && trustAccount;
  const trimmedComment = comment.trim();
  const commentRequired = isApprove && (isRed || effectiveTrust);
  const commentTooShort =
    commentRequired && trimmedComment.length < MIN_DIRECTOR_COMMENT_LENGTH;

  const minCharsLabel = plural(
    MIN_DIRECTOR_COMMENT_LENGTH,
    t.plurals.charsGenitive
  );

  const isSubmitDisabled =
    isSubmitting || (isApprove && (isInvalid || commentTooShort));

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen && isSubmitting) return;
    if (!nextOpen) {
      setError(null);
      setComment("");
      setTrustAccount(false);
    }
    onOpenChange(nextOpen);
  };

  const handleSubmit = async () => {
    if (isSubmitDisabled) return;
    setError(null);
    setIsSubmitting(true);
    try {
      const updated = await decideApproval(
        approvalId,
        {
          decision,
          director_comment: trimmedComment,
          trust_account: effectiveTrust,
        },
        lang
      );
      notifyProdApprovalsUpdated();
      notify.success(
        decision === "approved"
          ? t.prod.approvals.decidedToastApproved
          : t.prod.approvals.decidedToastRejected,
        recipientName
          ? interpolate(t.toast.decisionSavedDescription, {
              recipient: recipientName,
            })
          : undefined
      );
      setComment("");
      setTrustAccount(false);
      onOpenChange(false);
      onDecided(updated);
    } catch (err) {
      const message = getProdErrorMessage(err);
      if (err instanceof ApiError && err.status === 409) {
        notify.warning(t.director.conflictTitle, message);
        onOpenChange(false);
        onConflict?.();
      } else {
        setError(message);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const subtitle =
    recipientName && amountDisplay
      ? interpolate(t.prod.approvals.dialogSubtitle, {
          recipient: recipientName,
          amount: amountDisplay,
        })
      : recipientName || undefined;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent mobileSheet className="sm:max-w-lg">
        <div
          aria-hidden="true"
          className="mx-auto -mt-1 mb-1 h-1.5 w-10 rounded-full bg-border sm:hidden"
        />

        <DialogHeader>
          <DialogTitle>
            {isApprove
              ? t.prod.approvals.dialogApproveTitle
              : t.prod.approvals.dialogRejectTitle}
          </DialogTitle>
          {subtitle && <DialogDescription>{subtitle}</DialogDescription>}
        </DialogHeader>

        <div className="space-y-4">
          {allowDecisionSwitch && (
            <div className="grid grid-cols-2 gap-2">
              <Button
                type="button"
                variant="outline"
                aria-pressed={isApprove}
                onClick={() => {
                  setDecision("approved");
                  setError(null);
                }}
                disabled={isSubmitting}
                className={cn(
                  "min-h-11 sm:min-h-9",
                  isApprove && "border-foreground bg-muted font-semibold"
                )}
              >
                {t.director.approve}
              </Button>
              <Button
                type="button"
                variant="outline"
                aria-pressed={!isApprove}
                onClick={() => {
                  setDecision("rejected");
                  setTrustAccount(false);
                  setError(null);
                }}
                disabled={isSubmitting}
                className={cn(
                  "min-h-11 sm:min-h-9",
                  !isApprove &&
                    "border-[#E5A3A3] bg-[#FEF2F2] font-semibold text-[#B91C1C]"
                )}
              >
                {t.director.reject}
              </Button>
            </div>
          )}

          {isApprove && isInvalid && (
            <Alert variant="destructive">
              <AlertCircle className="size-4" />
              <AlertDescription className="break-words">
                {t.prod.approvals.invalidCannotApprove}
              </AlertDescription>
            </Alert>
          )}

          {error && (
            <Alert variant="destructive">
              <AlertCircle className="size-4" />
              <AlertDescription className="break-words">
                {error}
              </AlertDescription>
            </Alert>
          )}

          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Label htmlFor={`prod-decision-comment-${approvalId}`}>
                {t.director.directorCommentLabel}
                {commentRequired && (
                  <span className="ml-1 font-semibold text-[var(--status-danger-text)]">
                    *
                  </span>
                )}
              </Label>
              {commentRequired && (
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
              id={`prod-decision-comment-${approvalId}`}
              rows={3}
              aria-required={commentRequired}
              className="min-h-24 w-full"
              placeholder={
                commentRequired
                  ? interpolate(t.director.commentPlaceholderRequired, {
                      minChars: minCharsLabel,
                    })
                  : t.director.commentPlaceholderOptional
              }
              value={comment}
              onChange={(e) => {
                setComment(e.target.value);
                if (error) setError(null);
              }}
              disabled={isSubmitting}
            />

            {commentRequired && (
              <p className="text-xs text-muted-foreground">
                {t.director.rejectNoCommentHint}
              </p>
            )}
          </div>

          {isApprove && canTrust && (
            <div className="ui-subpanel flex min-h-11 items-start gap-3">
              <Checkbox
                id={`prod-trust-account-${approvalId}`}
                checked={trustAccount}
                onCheckedChange={(checked) => {
                  setTrustAccount(Boolean(checked));
                  if (error) setError(null);
                }}
                disabled={isSubmitting}
                className="mt-0.5"
              />
              <div className="min-w-0 flex-1 space-y-0.5">
                <Label
                  htmlFor={`prod-trust-account-${approvalId}`}
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
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => handleOpenChange(false)}
            disabled={isSubmitting}
            className="min-h-11 w-full sm:min-h-9 sm:w-auto"
          >
            {t.common.cancel}
          </Button>
          <Button
            type="button"
            variant={isApprove ? "default" : "destructive"}
            disabled={isSubmitDisabled}
            onClick={() => void handleSubmit()}
            className="min-h-11 w-full sm:min-h-9 sm:w-auto"
          >
            {isSubmitting ? (
              <>
                <Loader2 className="size-4 animate-spin" />
                <span>
                  {isApprove ? t.director.saving : t.director.rejecting}
                </span>
              </>
            ) : isApprove ? (
              <span>{t.director.approve}</span>
            ) : (
              <span>{t.director.reject}</span>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
