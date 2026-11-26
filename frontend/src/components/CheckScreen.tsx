"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  ArrowLeft,
  Clock,
  FileEdit,
  Loader2,
  PauseCircle,
  RefreshCw,
  Send,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { AdviceBox } from "@/components/AdviceBox";
import { ComparisonTable } from "@/components/ComparisonTable";
import { ReasonsList } from "@/components/ReasonsList";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
  isNetworkUnreachableError,
} from "@/lib/api";
import {
  APPROVAL_STATUS_STYLES,
  findApprovalForPayment,
} from "@/lib/approvals";
import {
  pickActionText,
  pickHeadline,
  VERDICT_STYLES,
} from "@/lib/format";
import { notify } from "@/lib/toast";
import type { Approval, CheckRequest, CheckResult } from "@/lib/types";
import { cn } from "cn";

interface CheckScreenProps {
  request: CheckRequest;
  result: CheckResult;
  approvals: Approval[];
  onBack: () => void;
  onFixRequisites?: (request: CheckRequest) => void;
  onResultUpdate?: (updatedResult: CheckResult) => void;
  onApprovalCreated?: (approval: Approval) => void;
  onNetworkError?: (message: string) => void;
}

export function CheckScreen({
  request,
  result,
  approvals,
  onBack,
  onFixRequisites,
  onResultUpdate,
  onApprovalCreated,
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
  const [recheckError, setRecheckError] = useState<string | null>(null);
  const [demoActionStatus, setDemoActionStatus] = useState<
    "signed" | "postponed" | null
  >(null);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [accountantNote, setAccountantNote] = useState("");
  const [isSendingApproval, setIsSendingApproval] = useState(false);
  const [dialogError, setDialogError] = useState<string | null>(null);

  const [sentApprovalId, setSentApprovalId] = useState<string | null>(null);
  const [localApproval, setLocalApproval] = useState<Approval | null>(null);

  const lastFetchedLangRef = useRef(lang);
  const baseCheckIdRef = useRef(result.check_id);
  const onNetworkErrorRef = useRef(onNetworkError);

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

    checkPayment(request, lang)
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
  const showTrustedBanner = isTrusted || Boolean(currentResult.trusted_info);

  const handleRecheck = async () => {
    setIsRechecking(true);
    setRecheckError(null);
    try {
      const updated = await checkPayment(request, lang);
      lastFetchedLangRef.current = lang;
      setOverride({ baseCheckId: result.check_id, result: updated });
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

  const handleSignDemo = () => {
    setRecheckError(null);
    setDemoActionStatus("signed");
    notify.success(
      t.toast.signedTitle,
      interpolate(t.toast.signedDescription, {
        amount: formatMoney(request.amount_kzt),
        recipient: request.recipient_name,
      })
    );
  };

  const handlePostponeDemo = () => {
    setRecheckError(null);
    setDemoActionStatus("postponed");
    notify.warning(t.toast.postponedTitle, t.toast.postponedDescription);
  };

  const handleSendToDirector = async () => {
    if (isSendingApproval || isPendingApproval || sentApprovalId !== null) {
      return;
    }

    setDialogError(null);
    setIsSendingApproval(true);
    try {
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
      if (isNetworkUnreachableError(err)) {
        setDialogOpen(false);
        onNetworkError?.(message);
        notify.error(t.common.serverErrorTitle, message);
      } else {
        setDialogError(message);
        notify.error(t.check.actionErrorTitle, message);
      }
    } finally {
      setIsSendingApproval(false);
    }
  };

  const verdict = currentResult.verdict;
  const resolvedApprovalStatus = effectiveApproval?.status ?? approvalStatus;
  const approvalStyle = resolvedApprovalStatus
    ? APPROVAL_STATUS_STYLES[resolvedApprovalStatus]
    : null;
  const approvalLabel = resolvedApprovalStatus
    ? t.approvalStatus[resolvedApprovalStatus]
    : null;
  const directorComment = effectiveApproval?.director_comment?.trim() || null;

  const invalidBtnClass =
    VERDICT_STYLES.invalid.actionButtonClass ??
    "bg-rose-900 text-white hover:bg-rose-950";
  const redBtnClass =
    VERDICT_STYLES.red.actionButtonClass ??
    "bg-red-600 text-white hover:bg-red-700";

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
          size="lg"
          onClick={() =>
            onFixRequisites ? onFixRequisites(request) : onBack()
          }
          className={cn("min-h-11 w-full gap-2", invalidBtnClass)}
        >
          <FileEdit className="size-4" />
          <span>{t.check.actionFixRequisites}</span>
        </Button>
      );
    }

    if (isRejectedByDirector) {
      return (
        <div className="rounded-xl border border-red-300 bg-red-50 p-3.5 text-sm text-red-950 space-y-1">
          <div className="flex items-center gap-2 font-semibold text-red-800">
            <XCircle className="size-4 shrink-0" />
            <span>{t.check.rejectedTitle}</span>
          </div>
          {directorComment && (
            <p className="text-xs text-red-900 break-words">
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
            size="lg"
            onClick={handleSignDemo}
            className="min-h-11 w-full gap-2"
          >
            <ShieldCheck className="size-4" />
            <span>{t.check.actionSign}</span>
          </Button>
          <p className="text-xs text-[#006B49]">
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
              size="lg"
              onClick={handlePostponeDemo}
              className={cn("min-h-11 w-full gap-2", redBtnClass)}
            >
              <PauseCircle className="size-4" />
              <span>{t.check.actionPostpone}</span>
            </Button>
            <Button
              type="button"
              variant="outline"
              size="lg"
              disabled
              className="min-h-11 w-full gap-2"
            >
              <Clock className="size-4" />
              <span>{t.check.actionSentToDirector}</span>
            </Button>
            <p className="pt-1 text-xs text-muted-foreground">
              {t.check.blockedUntilDecisionHint}
            </p>
          </div>
        );
      }

      if (verdict === "green") {
        return (
          <div className="space-y-2">
            <Button
              type="button"
              size="lg"
              onClick={handleSignDemo}
              className="min-h-11 w-full gap-2"
            >
              <ShieldCheck className="size-4" />
              <span>{t.check.actionSign}</span>
            </Button>
            <Button
              type="button"
              variant="outline"
              size="lg"
              disabled
              className="min-h-11 w-full gap-2"
            >
              <Clock className="size-4" />
              <span>{t.check.actionSentToDirector}</span>
            </Button>
          </div>
        );
      }

      return (
        <div className="space-y-2">
          <Button
            type="button"
            size="lg"
            disabled
            className="min-h-11 w-full gap-2"
          >
            <Clock className="size-4" />
            <span>{t.check.actionSentToDirector}</span>
          </Button>
          <Button
            type="button"
            variant="outline"
            size="lg"
            onClick={handleSignDemo}
            className="min-h-11 w-full gap-2"
          >
            <ShieldCheck className="size-4" />
            <span>{t.check.actionSign}</span>
          </Button>
        </div>
      );
    }

    if (verdict === "green") {
      return (
        <Button
          type="button"
          size="lg"
          onClick={handleSignDemo}
          className="min-h-11 w-full gap-2"
        >
          <ShieldCheck className="size-4" />
          <span>{t.check.actionSign}</span>
        </Button>
      );
    }

    if (verdict === "red") {
      return (
        <div className="space-y-2">
          <Button
            type="button"
            size="lg"
            onClick={handlePostponeDemo}
            className={cn("min-h-11 w-full gap-2", redBtnClass)}
          >
            <PauseCircle className="size-4" />
            <span>{t.check.actionPostpone}</span>
          </Button>
          <Button
            type="button"
            variant="outline"
            size="lg"
            onClick={openDirectorDialog}
            className="min-h-11 w-full gap-2"
          >
            <Send className="size-4" />
            <span>{t.check.actionSendToDirector}</span>
          </Button>
          <p className="pt-1 text-xs text-muted-foreground">
            {t.check.blockedUntilCheckOrApprovalHint}
          </p>
        </div>
      );
    }

    return (
      <div className="space-y-2">
        <Button
          type="button"
          size="lg"
          onClick={openDirectorDialog}
          className="min-h-11 w-full gap-2"
        >
          <Send className="size-4" />
          <span>{t.check.actionSendToDirector}</span>
        </Button>
        <Button
          type="button"
          variant="outline"
          size="lg"
          onClick={handleSignDemo}
          className="min-h-11 w-full gap-2"
        >
          <ShieldCheck className="size-4" />
          <span>{t.check.actionSign}</span>
        </Button>
      </div>
    );
  };

  const renderPrimaryMobileAction = () => {
    if (verdict === "invalid") {
      return (
        <Button
          type="button"
          size="lg"
          onClick={() =>
            onFixRequisites ? onFixRequisites(request) : onBack()
          }
          className={cn("min-h-11 w-full gap-2", invalidBtnClass)}
        >
          <FileEdit className="size-4" />
          <span>{t.check.actionFixRequisites}</span>
        </Button>
      );
    }

    if (isRejectedByDirector) {
      return null;
    }

    if (isApprovedByDirector || verdict === "green") {
      return (
        <Button
          type="button"
          size="lg"
          onClick={handleSignDemo}
          className="min-h-11 w-full gap-2"
        >
          <ShieldCheck className="size-4" />
          <span>{t.check.actionSign}</span>
        </Button>
      );
    }

    if (verdict === "red") {
      return (
        <Button
          type="button"
          size="lg"
          onClick={handlePostponeDemo}
          className={cn("min-h-11 w-full gap-2", redBtnClass)}
        >
          <PauseCircle className="size-4" />
          <span>{t.check.actionPostpone}</span>
        </Button>
      );
    }

    if (isPendingApproval) {
      return (
        <Button
          type="button"
          size="lg"
          disabled
          className="min-h-11 w-full gap-2"
        >
          <Clock className="size-4" />
          <span>{t.check.actionSentToDirector}</span>
        </Button>
      );
    }

    return (
      <Button
        type="button"
        size="lg"
        onClick={openDirectorDialog}
        className="min-h-11 w-full gap-2"
      >
        <Send className="size-4" />
        <span>{t.check.actionSendToDirector}</span>
      </Button>
    );
  };

  const mobilePrimaryAction = renderPrimaryMobileAction();

  return (
    <div
      className={cn(
        "space-y-5",
        mobilePrimaryAction &&
          "pb-[calc(5.5rem+env(safe-area-inset-bottom))] md:pb-0"
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2.5 sm:gap-3">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={onBack}
          className="min-h-11 gap-1.5 text-muted-foreground hover:text-foreground sm:min-h-9"
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
          className="min-h-11 gap-1.5 sm:min-h-9"
        >
          <RefreshCw
            className={cn("size-3.5", isRechecking && "animate-spin")}
          />
          <span>{isRechecking ? t.check.rechecking : t.check.recheck}</span>
        </Button>
      </div>

      <Card className="min-w-0">
        <CardContent className="flex flex-col gap-3 py-4 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between sm:gap-4">
          <div className="min-w-0 flex-1 space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                {t.check.paymentOrderEyebrow}
              </span>
              {approvalStyle && approvalLabel && (
                <Badge
                  variant="outline"
                  className={cn(
                    "h-auto px-2 py-0.5 text-xs font-medium",
                    approvalStyle.badgeClass
                  )}
                >
                  {approvalLabel}
                </Badge>
              )}
            </div>
            <div className="text-lg font-semibold text-foreground break-words">
              {request.recipient_name}
            </div>
            <div className="text-sm text-muted-foreground break-words">
              {request.purpose}
            </div>
            {directorComment && (
              <div className="rounded-lg border border-border bg-muted/50 px-3 py-1.5 text-xs text-foreground break-words">
                <span className="font-semibold">
                  {t.check.directorCommentLabel}
                </span>
                <span>{directorComment}</span>
              </div>
            )}
          </div>

          <div className="min-w-0 shrink-0 space-y-1 text-left sm:text-right">
            <div className="text-2xl font-bold tabular-nums text-foreground">
              {formatMoney(request.amount_kzt)}
            </div>
            <div className="text-xs text-muted-foreground space-y-1">
              <div>
                {(currentResult.history?.payments_count ?? 0) > 0
                  ? interpolate(t.check.historySummary, {
                      count: currentResult.history.payments_count,
                      date: formatDate(currentResult.history.last_payment_date),
                    })
                  : t.check.noPriorPayments}
              </div>
              {currentResult.history?.compared_with && (
                <div className="inline-block max-w-full rounded-md border border-amber-200 bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-900 break-words">
                  {interpolate(t.check.comparedWith, {
                    supplier: currentResult.history.compared_with,
                  })}
                </div>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      <VerdictBanner
        verdict={verdict}
        headline={pickHeadline(currentResult)}
      />

      {showTrustedBanner && (
        <Alert className="rounded-xl border-[#00AB75]/35 bg-[#E8F8F2] text-[#064A34]">
          <ShieldCheck className="size-4 text-[var(--brand-text)]" />
          <AlertTitle>{t.check.trustedBannerTitle}</AlertTitle>
          <AlertDescription className="text-[#064A34]/90 font-medium break-words">
            {formatTrustedBanner(currentResult.trusted_info)}
          </AlertDescription>
        </Alert>
      )}

      {recheckError && (
        <Alert variant="destructive" className="rounded-xl bg-red-50/90 border-red-300">
          <AlertCircle className="size-4" />
          <AlertTitle>{t.check.actionErrorTitle}</AlertTitle>
          <AlertDescription className="break-words">
            {recheckError}
          </AlertDescription>
        </Alert>
      )}

      {isRejectedByDirector && (
        <Alert className="rounded-xl border-red-300 bg-red-50 text-red-950">
          <XCircle className="size-4 text-red-600" />
          <AlertTitle>{t.check.rejectedTitle}</AlertTitle>
          <AlertDescription className="text-red-900 break-words">
            {directorComment
              ? interpolate(t.check.directorCommentLine, {
                  comment: directorComment,
                })
              : t.check.rejectedBlocked}
          </AlertDescription>
        </Alert>
      )}

      <div className="grid grid-cols-1 items-start gap-5 lg:grid-cols-[minmax(0,1fr)_320px] xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="min-w-0 space-y-5">
          <ComparisonTable
            comparison={currentResult.comparison}
            trusted={isTrusted}
          />

          <ReasonsList
            signals={currentResult.signals}
            score={currentResult.score}
          />
        </div>

        <div className="min-w-0 space-y-4 lg:sticky lg:top-28">
          <AdviceBox
            text={pickActionText(currentResult.next_action)}
            verdict={verdict}
          />

          <Card className="min-w-0">
            <CardContent className="pt-4 space-y-2.5">
              <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {t.check.actionsEyebrow}
              </div>
              {renderActionButtons()}
              {demoActionStatus === "signed" && (
                <div
                  role="status"
                  className="rounded-xl border border-[#00AB75]/35 bg-[#E8F8F2] px-3 py-2 text-xs font-medium text-[#064A34]"
                >
                  {t.check.signedStatusNote}
                </div>
              )}
              {demoActionStatus === "postponed" && (
                <div
                  role="status"
                  className="rounded-xl border border-amber-300 bg-amber-50 px-3 py-2 text-xs font-medium text-amber-950"
                >
                  {t.check.postponedStatusNote}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {mobilePrimaryAction && (
        <div className="fixed inset-x-0 bottom-0 z-30 border-t border-border bg-card/95 px-4 pt-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))] shadow-[0_-4px_16px_rgba(29,29,30,0.08)] backdrop-blur supports-[backdrop-filter]:bg-card/90 md:hidden">
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
              <Alert variant="destructive">
                <AlertCircle className="size-4" />
                <AlertDescription className="break-words">
                  {dialogError}
                </AlertDescription>
              </Alert>
            )}

            <div className="rounded-lg border border-border bg-background/80 px-3 py-2 text-xs space-y-0.5">
              <div className="font-medium text-foreground break-words">
                {request.recipient_name}
              </div>
              <div className="flex flex-wrap items-baseline gap-x-1.5 text-muted-foreground">
                <span className="tabular-nums">
                  {formatMoney(request.amount_kzt)}
                </span>
                <span aria-hidden="true">·</span>
                <span className="font-mono break-all">
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
                placeholder={t.check.accountantNotePlaceholder}
                value={accountantNote}
                onChange={(e) => setAccountantNote(e.target.value)}
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setDialogOpen(false)}
              disabled={isSendingApproval}
              className="min-h-11 w-full sm:min-h-9 sm:w-auto"
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
              className="min-h-11 w-full gap-1.5 sm:min-h-9 sm:w-auto"
            >
              {isSendingApproval ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  <span>{t.check.sending}</span>
                </>
              ) : (
                <>
                  <Send className="size-4" />
                  <span>{t.check.send}</span>
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
