"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Loader2 } from "lucide-react";
import { AdviceBox } from "@/components/AdviceBox";
import { ComparisonTable } from "@/components/ComparisonTable";
import { ExplainButton } from "@/components/ExplainButton";
import { NewPaymentDialog } from "@/components/NewPaymentDialog";
import { ReasonsList } from "@/components/ReasonsList";
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
import { VerdictBanner } from "@/components/VerdictBanner";
import { useT } from "@/i18n";
import {
  checkPayment,
  createApproval,
  getErrorMessage,
  getFieldErrors,
  isNetworkUnreachableError,
} from "@/lib/api";
import {
  APPROVAL_STATUS_STYLES,
  findApprovalForPayment,
} from "@/lib/approvals";
import {
  extractInvalidFieldMap,
  pickActionText,
  pickHeadline,
} from "@/lib/format";
import { hasIdentitySignal } from "@/lib/identitySignals";
import { notify } from "@/lib/toast";
import type {
  Approval,
  ApprovalStatus,
  CheckRequest,
  CheckResult,
  SignPaymentPayload,
  Verdict,
} from "@/lib/types";
import { cn } from "cn";

const APPROVAL_DOT_CLASS: Record<ApprovalStatus, string> = {
  pending: "ui-dot-warn",
  approved: "ui-dot-ok",
  rejected: "ui-dot-danger",
};

interface CheckScreenProps {
  paymentId?: string;
  request: CheckRequest;
  result: CheckResult;
  approvals: Approval[];
  onBack: () => void;
  onFixRequisites?: (request: CheckRequest) => void;
  onPaymentFixed?: (request: CheckRequest, result: CheckResult) => void;
  onResultUpdate?: (updatedResult: CheckResult) => void;
  onApprovalCreated?: (approval: Approval) => void;
  onSigned?: (payload: SignPaymentPayload) => void;
  onNetworkError?: (message: string) => void;
}

export function CheckScreen({
  paymentId,
  request,
  result,
  approvals,
  onBack,
  onFixRequisites,
  onPaymentFixed,
  onResultUpdate,
  onApprovalCreated,
  onSigned,
  onNetworkError,
}: CheckScreenProps) {
  const router = useRouter();
  const { t, lang, formatMoney, formatDate, interpolate, formatTrustedBanner } =
    useT();

  const [override, setOverride] = useState<{
    baseCheckId: string;
    result: CheckResult;
  } | null>(null);
  const currentResult =
    override && override.baseCheckId === result.check_id
      ? override.result
      : result;

  const [isRechecking, setIsRechecking] = useState(false);
  const [isSigning, setIsSigning] = useState(false);
  const [recheckError, setRecheckError] = useState<string | null>(null);
  const [signError, setSignError] = useState<string | null>(null);
  const [demoActionStatus, setDemoActionStatus] = useState<
    "signed" | "postponed" | null
  >(null);
  const [canUndoPostpone, setCanUndoPostpone] = useState(false);
  const [accountantAck, setAccountantAck] = useState(false);
  const [signedWithAck, setSignedWithAck] = useState(false);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [fixDialogOpen, setFixDialogOpen] = useState(false);
  const [accountantNote, setAccountantNote] = useState("");
  const [isSendingApproval, setIsSendingApproval] = useState(false);
  const [dialogError, setDialogError] = useState<string | null>(null);
  const [noteFieldError, setNoteFieldError] = useState<string | null>(null);

  const [sentApprovalId, setSentApprovalId] = useState<string | null>(null);
  const [localApproval, setLocalApproval] = useState<Approval | null>(null);

  const lastFetchedLangRef = useRef(lang);
  const baseCheckIdRef = useRef(result.check_id);
  const onNetworkErrorRef = useRef(onNetworkError);
  const postponeUndoTimerRef = useRef<number | null>(null);
  const previousStatusBeforePostponeRef = useRef<"signed" | "postponed" | null>(
    null
  );
  const signInFlightRef = useRef(false);
  const signCommittedRef = useRef(false);
  const approvalInFlightRef = useRef(false);
  const approvalCommittedRef = useRef(false);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [paymentId]);

  useEffect(() => {
    return () => {
      if (postponeUndoTimerRef.current !== null) {
        window.clearTimeout(postponeUndoTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    baseCheckIdRef.current = result.check_id;
  }, [result.check_id]);

  useEffect(() => {
    onNetworkErrorRef.current = onNetworkError;
  }, [onNetworkError]);

  useEffect(() => {
    if (lastFetchedLangRef.current === lang) return;
    lastFetchedLangRef.current = lang;
    let active = true;

    checkPayment(request, lang, { recordHistory: false })
      .then((updated) => {
        if (!active) return;
        setOverride({ baseCheckId: baseCheckIdRef.current, result: updated });
      })
      .catch((err) => {
        if (!active) return;
        if (isNetworkUnreachableError(err)) {
          onNetworkErrorRef.current?.(getErrorMessage(err));
        }
      });

    return () => {
      active = false;
    };
  }, [lang, request]);

  const matchedApproval = findApprovalForPayment(approvals, request);
  const effectiveApproval = matchedApproval ?? localApproval;
  const approvalStatus =
    effectiveApproval?.status ?? (sentApprovalId ? "pending" : null);

  const isPendingApproval = approvalStatus === "pending";
  const isApprovedByDirector = approvalStatus === "approved";
  const isRejectedByDirector = approvalStatus === "rejected";
  const isTrusted = currentResult.trusted === true;
  const hasTrustedInfo = isTrusted || Boolean(currentResult.trusted_info);

  const verdict = currentResult.verdict;
  const showProminentTrustedBanner = hasTrustedInfo && verdict === "green";
  const showSecondaryTrustedNote = hasTrustedInfo && verdict !== "green";
  const invalidFields = extractInvalidFieldMap(verdict, currentResult.signals);
  const hasRecipientIdentityDoubt = hasIdentitySignal(currentResult.signals);
  const isYellowOrGrey = verdict === "yellow" || verdict === "grey";
  const requiresDirectorForIdentity =
    isYellowOrGrey &&
    hasRecipientIdentityDoubt &&
    !isApprovedByDirector &&
    !isPendingApproval &&
    !isRejectedByDirector;
  const requiresAccountantAck =
    isYellowOrGrey &&
    !hasRecipientIdentityDoubt &&
    !isApprovedByDirector &&
    !isPendingApproval &&
    !isRejectedByDirector;

  const canSign =
    verdict !== "invalid" &&
    !isRejectedByDirector &&
    !isPendingApproval &&
    (isApprovedByDirector ||
      verdict === "green" ||
      (requiresAccountantAck && accountantAck));

  const handleRecheck = async () => {
    setIsRechecking(true);
    setRecheckError(null);
    try {
      const updated = await checkPayment(request, lang, {
        historyAction: "recheck",
      });
      lastFetchedLangRef.current = lang;
      setOverride({ baseCheckId: result.check_id, result: updated });
      setAccountantAck(false);
      setDemoActionStatus(null);
      setCanUndoPostpone(false);
      if (postponeUndoTimerRef.current !== null) {
        window.clearTimeout(postponeUndoTimerRef.current);
        postponeUndoTimerRef.current = null;
      }
      setSignedWithAck(false);
      onResultUpdate?.(updated);
      notify.success(t.toast.recheckTitle, t.toast.recheckDescription);
    } catch (err) {
      const message = getErrorMessage(err);
      if (isNetworkUnreachableError(err)) {
        onNetworkError?.(message);
      } else {
        setRecheckError(message);
        notify.error(t.check.actionErrorTitle, message);
      }
    } finally {
      setIsRechecking(false);
    }
  };

  const handleSignDemo = async () => {
    if (
      !canSign ||
      isSigning ||
      signInFlightRef.current ||
      demoActionStatus === "signed"
    ) {
      return;
    }

    signInFlightRef.current = true;
    setIsSigning(true);
    setRecheckError(null);
    setSignError(null);

    try {
      let effectiveCheckId = currentResult.check_id;
      let effectiveVerdict: Verdict = verdict;

      if (!signCommittedRef.current) {
        const committed = await checkPayment(request, lang, { commit: true });
        signCommittedRef.current = true;
        effectiveCheckId = committed.check_id;
        effectiveVerdict = committed.verdict;
        lastFetchedLangRef.current = lang;
        setOverride({ baseCheckId: result.check_id, result: committed });
        onResultUpdate?.(committed);
      }

      const ack = requiresAccountantAck && accountantAck;
      const signPayload: SignPaymentPayload = {
        check_id: effectiveCheckId,
        verdict: effectiveVerdict,
        request,
        accountant_ack: ack,
        approval_id: effectiveApproval?.id ?? null,
      };

      if (typeof window !== "undefined") {
        window.dispatchEvent(
          new CustomEvent<SignPaymentPayload>("business-shield:sign", {
            detail: signPayload,
          })
        );
      }
      onSigned?.(signPayload);

      setSignedWithAck(ack);
      setDemoActionStatus("signed");
      notify.success(
        t.toast.signedTitle,
        interpolate(t.toast.signedDescription, {
          amount: formatMoney(request.amount_kzt),
          recipient: request.recipient_name,
        })
      );
    } catch (err) {
      const message = getErrorMessage(err);
      setSignError(message);
      setRecheckError(message);
      if (isNetworkUnreachableError(err)) {
        onNetworkError?.(message);
        notify.error(t.common.serverErrorTitle, message);
      } else {
        notify.error(t.check.actionErrorTitle, message);
      }
    } finally {
      signInFlightRef.current = false;
      setIsSigning(false);
    }
  };

  const handleUndoPostpone = () => {
    if (postponeUndoTimerRef.current !== null) {
      window.clearTimeout(postponeUndoTimerRef.current);
      postponeUndoTimerRef.current = null;
    }
    setCanUndoPostpone(false);
    setDemoActionStatus(previousStatusBeforePostponeRef.current);
    previousStatusBeforePostponeRef.current = null;
    notify.info(t.toast.postponeUndoneTitle, t.toast.postponeUndoneDescription);
  };

  const handlePostponeDemo = () => {
    setRecheckError(null);
    if (postponeUndoTimerRef.current !== null) {
      window.clearTimeout(postponeUndoTimerRef.current);
    }
    if (demoActionStatus !== "postponed") {
      previousStatusBeforePostponeRef.current = demoActionStatus;
    }
    setDemoActionStatus("postponed");
    setCanUndoPostpone(true);
    postponeUndoTimerRef.current = window.setTimeout(() => {
      setCanUndoPostpone(false);
      postponeUndoTimerRef.current = null;
    }, 5000);

    notify.warning(t.toast.postponedTitle, {
      description: t.toast.postponedDescription,
      duration: 5000,
      action: {
        label: t.common.undo,
        onClick: () => {
          handleUndoPostpone();
        },
      },
    });
  };

  const handleOpenFixRequisites = () => {
    if (onPaymentFixed) {
      setFixDialogOpen(true);
      return;
    }
    if (onFixRequisites) {
      onFixRequisites(request);
      return;
    }
    onBack();
  };

  const handleSendToDirector = async () => {
    if (
      approvalInFlightRef.current ||
      isSendingApproval ||
      isPendingApproval ||
      sentApprovalId !== null
    ) {
      return;
    }

    approvalInFlightRef.current = true;
    setDialogError(null);
    setNoteFieldError(null);
    setIsSendingApproval(true);
    try {
      if (!approvalCommittedRef.current) {
        const committed = await checkPayment(request, lang, { commit: true });
        approvalCommittedRef.current = true;
        lastFetchedLangRef.current = lang;
        setOverride({ baseCheckId: result.check_id, result: committed });
        onResultUpdate?.(committed);
      }

      const created = await createApproval(
        {
          request,
          accountant_note: accountantNote.trim(),
        },
        lang
      );
      setSentApprovalId(created.id);
      setLocalApproval(created);
      setDialogOpen(false);
      setAccountantNote("");
      setNoteFieldError(null);
      onApprovalCreated?.(created);
      notify.success(t.toast.sentToDirectorTitle, {
        description: t.toast.sentToDirectorDescription,
        action: {
          label: t.common.openApprovals,
          onClick: () => router.push("/approvals"),
        },
      });
    } catch (err) {
      const message = getErrorMessage(err);
      const fieldErrors = getFieldErrors(err);
      if (isNetworkUnreachableError(err)) {
        setDialogError(message);
        onNetworkError?.(message);
        notify.error(t.common.serverErrorTitle, message);
      } else {
        if (fieldErrors.accountant_note) {
          setNoteFieldError(fieldErrors.accountant_note);
        }
        setDialogError(message);
        notify.error(t.check.actionErrorTitle, message);
      }
    } finally {
      approvalInFlightRef.current = false;
      setIsSendingApproval(false);
    }
  };

  const resolvedApprovalStatus = effectiveApproval?.status ?? approvalStatus;
  const approvalStyle = resolvedApprovalStatus
    ? APPROVAL_STATUS_STYLES[resolvedApprovalStatus]
    : null;
  const approvalLabel = resolvedApprovalStatus
    ? t.approvalStatus[resolvedApprovalStatus]
    : null;
  const directorComment = effectiveApproval?.director_comment?.trim() || null;

  const openDirectorDialog = () => {
    if (isPendingApproval || sentApprovalId !== null) {
      return;
    }
    setDialogError(null);
    setDialogOpen(true);
  };

  const renderActionButtons = () => {
    if (verdict === "invalid") {
      return (
        <Button
          type="button"
          variant="destructive"
          onClick={handleOpenFixRequisites}
          className="hidden min-h-10 w-full md:inline-flex"
        >
          {t.check.actionFixRequisites}
        </Button>
      );
    }

    if (isRejectedByDirector) {
      return (
        <div className="ui-notice ui-notice-danger space-y-1 text-sm">
          <div className="font-semibold text-[var(--status-danger-text)]">
            {t.check.rejectedTitle}
          </div>
          {directorComment && (
            <p className="text-xs text-foreground break-words">
              {interpolate(t.check.directorCommentLine, {
                comment: directorComment,
              })}
            </p>
          )}
        </div>
      );
    }

    if (isApprovedByDirector) {
      return (
        <div className="space-y-2">
          <Button
            type="button"
            disabled={isSigning || demoActionStatus === "signed"}
            onClick={() => void handleSignDemo()}
            className="hidden min-h-10 w-full md:inline-flex"
          >
            {isSigning ? (
              <>
                <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                <span>{t.check.actionSigning}</span>
              </>
            ) : (
              t.check.actionSign
            )}
          </Button>
          <p className="text-xs text-[var(--status-ok-text)]">
            {t.check.approvedAllowedHint}
          </p>
        </div>
      );
    }

    if (isPendingApproval) {
      if (verdict === "red") {
        return (
          <div className="space-y-2">
            <Button
              type="button"
              variant="destructive"
              onClick={handlePostponeDemo}
              className="hidden min-h-10 w-full md:inline-flex"
            >
              {t.check.actionPostpone}
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled
              className="min-h-10 w-full"
            >
              {t.check.actionSentToDirector}
            </Button>
            <p className="pt-0.5 text-xs text-muted-foreground">
              {t.check.blockedUntilDecisionHint}
            </p>
          </div>
        );
      }

      return (
        <div className="space-y-2">
          <Button
            type="button"
            disabled
            className="hidden min-h-10 w-full md:inline-flex"
          >
            {t.check.actionSentToDirector}
          </Button>
          <Button
            type="button"
            variant="outline"
            disabled
            className="min-h-10 w-full"
          >
            {t.check.actionSign}
          </Button>
          <p className="pt-0.5 text-xs text-muted-foreground">
            {t.check.blockedUntilDecisionHint}
          </p>
        </div>
      );
    }

    if (verdict === "green") {
      return (
        <Button
          type="button"
          disabled={isSigning || demoActionStatus === "signed"}
          onClick={() => void handleSignDemo()}
          className="hidden min-h-10 w-full md:inline-flex"
        >
          {isSigning ? (
            <>
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              <span>{t.check.actionSigning}</span>
            </>
          ) : (
            t.check.actionSign
          )}
        </Button>
      );
    }

    if (verdict === "red") {
      return (
        <div className="space-y-2">
          <Button
            type="button"
            variant="destructive"
            onClick={handlePostponeDemo}
            className="hidden min-h-10 w-full md:inline-flex"
          >
            {t.check.actionPostpone}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={openDirectorDialog}
            className="min-h-10 w-full"
          >
            {t.check.actionSendToDirector}
          </Button>
          <p className="pt-0.5 text-xs text-muted-foreground">
            {t.check.blockedUntilCheckOrApprovalHint}
          </p>
        </div>
      );
    }

    if (requiresDirectorForIdentity) {
      return (
        <div className="space-y-2.5">
          <Button
            type="button"
            onClick={openDirectorDialog}
            className="hidden min-h-10 w-full md:inline-flex"
          >
            {t.check.actionSendToDirector}
          </Button>

          <div
            role="status"
            className="ui-notice ui-notice-warn py-2.5 text-xs leading-snug text-foreground break-words"
          >
            {t.check.directorRequiredIdentity}
          </div>

          <Button
            type="button"
            variant="outline"
            disabled
            className="min-h-10 w-full"
          >
            {t.check.actionSign}
          </Button>
        </div>
      );
    }

    return (
      <div className="space-y-2.5">
        <Button
          type="button"
          onClick={openDirectorDialog}
          className="hidden min-h-10 w-full md:inline-flex"
        >
          {t.check.actionSendToDirector}
        </Button>

        <div className="ui-subpanel flex min-h-10 items-start gap-2.5">
          <Checkbox
            id="accountant-ack-checkbox"
            checked={accountantAck}
            disabled={isSigning || demoActionStatus === "signed"}
            onCheckedChange={(checked) => setAccountantAck(Boolean(checked))}
            className="mt-0.5"
          />
          <div className="min-w-0 flex-1 space-y-0.5">
            <Label
              htmlFor="accountant-ack-checkbox"
              className="cursor-pointer text-xs font-medium leading-snug text-foreground"
            >
              {t.check.accountantAckLabel}
            </Label>
            {!accountantAck && (
              <p className="text-xs leading-snug text-muted-foreground">
                {t.check.accountantAckRequiredHint}
              </p>
            )}
          </div>
        </div>

        <Button
          type="button"
          variant="outline"
          disabled={
            !accountantAck || isSigning || demoActionStatus === "signed"
          }
          onClick={() => void handleSignDemo()}
          className="min-h-10 w-full"
        >
          {isSigning ? (
            <>
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              <span>{t.check.actionSigning}</span>
            </>
          ) : (
            t.check.actionSign
          )}
        </Button>
      </div>
    );
  };

  const renderPrimaryMobileAction = () => {
    if (verdict === "invalid") {
      return (
        <Button
          type="button"
          variant="destructive"
          onClick={handleOpenFixRequisites}
          className="min-h-11 w-full"
        >
          {t.check.actionFixRequisites}
        </Button>
      );
    }

    if (isRejectedByDirector) {
      return null;
    }

    if (isApprovedByDirector) {
      return (
        <Button
          type="button"
          disabled={isSigning || demoActionStatus === "signed"}
          onClick={() => void handleSignDemo()}
          className="min-h-11 w-full"
        >
          {isSigning ? (
            <>
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              <span>{t.check.actionSigning}</span>
            </>
          ) : (
            t.check.actionSign
          )}
        </Button>
      );
    }

    if (isPendingApproval) {
      if (verdict === "red") {
        return (
          <Button
            type="button"
            variant="destructive"
            onClick={handlePostponeDemo}
            className="min-h-11 w-full"
          >
            {t.check.actionPostpone}
          </Button>
        );
      }

      return (
        <Button type="button" disabled className="min-h-11 w-full">
          {t.check.actionSentToDirector}
        </Button>
      );
    }

    if (verdict === "green") {
      return (
        <Button
          type="button"
          disabled={isSigning || demoActionStatus === "signed"}
          onClick={() => void handleSignDemo()}
          className="min-h-11 w-full"
        >
          {isSigning ? (
            <>
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              <span>{t.check.actionSigning}</span>
            </>
          ) : (
            t.check.actionSign
          )}
        </Button>
      );
    }

    if (verdict === "red") {
      return (
        <Button
          type="button"
          variant="destructive"
          onClick={handlePostponeDemo}
          className="min-h-11 w-full"
        >
          {t.check.actionPostpone}
        </Button>
      );
    }

    return (
      <Button
        type="button"
        onClick={openDirectorDialog}
        className="min-h-11 w-full"
      >
        {t.check.actionSendToDirector}
      </Button>
    );
  };

  const mobilePrimaryAction = renderPrimaryMobileAction();
  const hideInlineActionsCardOnMobile =
    (verdict === "invalid" ||
      (verdict === "green" &&
        !isPendingApproval &&
        !isApprovedByDirector &&
        !isRejectedByDirector)) &&
    demoActionStatus === null &&
    signError === null;

  return (
    <div
      className={cn(
        "space-y-4 sm:space-y-5",
        mobilePrimaryAction &&
          "pb-[calc(5.5rem+env(safe-area-inset-bottom))] md:pb-0"
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2.5">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={onBack}
          className="min-h-10 gap-1.5 text-muted-foreground hover:text-foreground sm:min-h-8"
        >
          <ArrowLeft className="size-4" />
          <span>{t.check.backToList}</span>
        </Button>

        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={handleRecheck}
          disabled={isRechecking}
          className="min-h-10 sm:min-h-8"
        >
          {isRechecking && (
            <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
          )}
          <span>{isRechecking ? t.check.rechecking : t.check.recheck}</span>
        </Button>
      </div>

      <div className="ui-panel min-w-0 p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-start sm:justify-between sm:gap-4">
          <div className="min-w-0 flex-1 space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="ui-label-meta">
                {t.check.paymentOrderEyebrow}
              </span>
              {resolvedApprovalStatus && approvalStyle && approvalLabel && (
                <span className={cn("ui-status", approvalStyle.badgeClass)}>
                  <span
                    aria-hidden="true"
                    className={cn(
                      "ui-status-dot",
                      APPROVAL_DOT_CLASS[resolvedApprovalStatus]
                    )}
                  />
                  <span>{approvalLabel}</span>
                </span>
              )}
            </div>
            <h1 className="ui-page-title break-words">
              {request.recipient_name}
            </h1>
            <p className="text-sm text-[var(--text-secondary)] break-words">
              {request.purpose}
            </p>
            {directorComment && (
              <div className="ui-subpanel mt-2 text-xs text-foreground break-words">
                <span className="font-semibold">
                  {t.check.directorCommentLabel}
                </span>
                <span>{directorComment}</span>
              </div>
            )}
            {showSecondaryTrustedNote && (
              <div className="pt-1">
                <span className="ui-tag max-w-full whitespace-normal break-words">
                  {formatTrustedBanner(currentResult.trusted_info)}
                </span>
              </div>
            )}
          </div>

          <div className="min-w-0 shrink-0 space-y-1 text-left sm:text-right">
            <div className="text-[22px] leading-7 font-semibold tabular-nums whitespace-nowrap text-foreground sm:text-2xl sm:leading-[30px]">
              {formatMoney(request.amount_kzt)}
            </div>
            <div className="space-y-1 text-xs text-muted-foreground tabular-nums">
              <div>
                {(currentResult.history?.payments_count ?? 0) > 0
                  ? interpolate(t.check.historySummary, {
                      count: currentResult.history.payments_count,
                      date: formatDate(currentResult.history.last_payment_date),
                    })
                  : t.check.noPriorPayments}
              </div>
              {currentResult.history?.compared_with && (
                <div>
                  <span className="ui-tag max-w-full whitespace-normal break-words">
                    {interpolate(t.check.comparedWith, {
                      supplier: currentResult.history.compared_with,
                    })}
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      <VerdictBanner
        verdict={verdict}
        headline={pickHeadline(currentResult, lang)}
      />

      {showProminentTrustedBanner && (
        <div role="status" className="ui-notice ui-notice-ok space-y-0.5">
          <div className="text-[13px] font-semibold text-foreground">
            {t.check.trustedBannerTitle}
          </div>
          <p className="text-[13px] text-[var(--text-secondary)] break-words">
            {formatTrustedBanner(currentResult.trusted_info)}
          </p>
        </div>
      )}

      {recheckError && (
        <div role="alert" className="ui-notice ui-notice-danger space-y-0.5">
          <div className="text-[13px] font-semibold text-[var(--status-danger-text)]">
            {t.check.actionErrorTitle}
          </div>
          <p className="text-[13px] text-foreground break-words">
            {recheckError}
          </p>
        </div>
      )}

      {isRejectedByDirector && (
        <div role="status" className="ui-notice ui-notice-danger space-y-0.5">
          <div className="text-[13px] font-semibold text-[var(--status-danger-text)]">
            {t.check.rejectedTitle}
          </div>
          <p className="text-[13px] text-foreground break-words">
            {directorComment
              ? interpolate(t.check.directorCommentLine, {
                  comment: directorComment,
                })
              : t.check.rejectedBlocked}
          </p>
        </div>
      )}

      <div className="grid grid-cols-1 items-start gap-4 sm:gap-5 lg:grid-cols-[minmax(0,1fr)_320px] xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="min-w-0 space-y-4 sm:space-y-5">
          <ComparisonTable
            comparison={currentResult.comparison}
            trusted={isTrusted}
            invalidFields={invalidFields}
          />

          <ReasonsList
            signals={currentResult.signals}
            score={currentResult.score}
          />
        </div>

        <div className="min-w-0 space-y-4 lg:sticky lg:top-20">
          <AdviceBox
            text={pickActionText(currentResult.next_action, lang)}
            verdict={verdict}
          />

          {(verdict === "yellow" ||
            verdict === "red" ||
            verdict === "grey") && (
            <ExplainButton
              check={currentResult}
              lang={lang}
              labels={t.explain}
            />
          )}

          <div
            className={cn(
              "ui-panel min-w-0 space-y-2.5 p-4",
              hideInlineActionsCardOnMobile && "hidden md:block"
            )}
          >
            <div className="ui-label-meta">{t.check.actionsEyebrow}</div>
            {signError && (
              <div
                role="alert"
                className="ui-notice ui-notice-danger py-2 text-xs text-foreground break-words"
              >
                {signError}
              </div>
            )}
            {renderActionButtons()}
            {demoActionStatus === "signed" && (
              <div
                role="status"
                className="ui-notice ui-notice-ok py-2 text-xs font-medium text-foreground"
              >
                {signedWithAck
                  ? t.check.signedWithAckStatusNote
                  : t.check.signedStatusNote}
              </div>
            )}
            {demoActionStatus === "postponed" && (
              <div
                role="status"
                className="ui-notice ui-notice-warn flex flex-wrap items-center justify-between gap-2 py-2 text-xs font-medium text-foreground"
              >
                <div className="min-w-0 flex-1 space-y-0.5">
                  <div>{t.check.postponedStatusNote}</div>
                  {canUndoPostpone && (
                    <div className="font-normal text-muted-foreground">
                      {t.check.postponedUndoHint}
                    </div>
                  )}
                </div>
                {canUndoPostpone && (
                  <Button
                    type="button"
                    variant="outline"
                    size="xs"
                    onClick={handleUndoPostpone}
                    className="shrink-0"
                  >
                    {t.common.undo}
                  </Button>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {currentResult.ruleset_version && (
        <div className="text-right font-mono text-[11px] tabular-nums text-muted-foreground">
          {interpolate(t.check.rulesetVersion, {
            version: currentResult.ruleset_version,
          })}
        </div>
      )}

      {mobilePrimaryAction && (
        <div className="fixed inset-x-0 bottom-0 z-30 border-t border-border bg-card px-4 pt-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))] shadow-none md:hidden">
          <div className="mx-auto max-w-[1248px]">{mobilePrimaryAction}</div>
        </div>
      )}

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t.check.dialogTitle}</DialogTitle>
            <DialogDescription>{t.check.dialogDescription}</DialogDescription>
          </DialogHeader>

          <div className="min-w-0 space-y-3 py-1">
            {dialogError && (
              <div
                role="alert"
                className="ui-notice ui-notice-danger py-2 text-xs text-foreground break-words"
              >
                {dialogError}
              </div>
            )}

            <div className="ui-subpanel space-y-0.5 text-xs">
              <div className="font-medium text-foreground break-words">
                {request.recipient_name}
              </div>
              <div className="flex flex-wrap items-baseline gap-x-1.5 text-muted-foreground">
                <span className="tabular-nums whitespace-nowrap">
                  {formatMoney(request.amount_kzt)}
                </span>
                <span aria-hidden="true">·</span>
                <span className="font-mono tabular-nums break-all">
                  {request.recipient_iik}
                </span>
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="accountant_note">
                {t.check.accountantNoteLabel}
              </Label>
              <Textarea
                id="accountant_note"
                rows={3}
                aria-invalid={Boolean(noteFieldError)}
                placeholder={t.check.accountantNotePlaceholder}
                value={accountantNote}
                onChange={(e) => {
                  setAccountantNote(e.target.value);
                  if (noteFieldError) setNoteFieldError(null);
                }}
              />
              {noteFieldError && (
                <p className="text-xs font-medium text-[var(--status-danger-text)] break-words">
                  {noteFieldError}
                </p>
              )}
            </div>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setDialogOpen(false)}
              disabled={isSendingApproval}
              className="min-h-10 w-full sm:min-h-9 sm:w-auto"
            >
              {t.common.cancel}
            </Button>
            <Button
              type="button"
              onClick={handleSendToDirector}
              disabled={
                isSendingApproval ||
                isPendingApproval ||
                sentApprovalId !== null
              }
              className="min-h-10 w-full sm:min-h-9 sm:w-auto"
            >
              {isSendingApproval ? (
                <>
                  <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                  <span>{t.check.sending}</span>
                </>
              ) : (
                t.check.send
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {onPaymentFixed && (
        <NewPaymentDialog
          key={`fix-${paymentId ?? "item"}-${request.recipient_bin}-${request.recipient_iik}-${request.recipient_bik}-${request.amount_kzt}`}
          open={fixDialogOpen}
          onOpenChange={setFixDialogOpen}
          mode="edit"
          prefillRequest={request}
          invalidFields={invalidFields}
          onPaymentCreated={(updatedRequest, updatedResult) => {
            onPaymentFixed(updatedRequest, updatedResult);
          }}
          onNetworkError={(message) => onNetworkError?.(message)}
        />
      )}
    </div>
  );
}
