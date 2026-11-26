"use client";

import { useState } from "react";
import {
  AlertCircle,
  Ban,
  CheckCircle2,
  ClipboardCheck,
  FileEdit,
  Loader2,
  Lock,
  PauseCircle,
  RotateCcw,
  Send,
  ShieldCheck,
} from "lucide-react";
import { notifyProdApprovalsUpdated } from "@/components/prod/ProdShell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
  cancelPayment,
  getProdErrorMessage,
  postponePayment,
  resumePayment,
  sendPaymentToDirector,
  signPayment,
} from "@/lib/prod/api";
import type { Payment } from "@/lib/prod/types";
import { notify } from "@/lib/toast";

interface SignPanelProps {
  payment: Payment;
  onPaymentUpdated: (payment: Payment) => void;
  onVerdictChanged: (payment: Payment, detail: string) => void;
  onReloadPayment: () => Promise<void>;
  onOpenEdit: () => void;
  onOpenDecide?: () => void;
}

type NoteDialogKind = "send" | "postpone" | "cancel" | null;

export function SignPanel({
  payment,
  onPaymentUpdated,
  onVerdictChanged,
  onReloadPayment,
  onOpenEdit,
  onOpenDecide,
}: SignPanelProps) {
  const { t, lang, formatDate, interpolate } = useT();
  const { permissions } = payment;

  // Reset ack state whenever check_id changes without effect boilerplate.
  const [ackState, setAckState] = useState<{
    checkId: string;
    checked: boolean;
  }>({ checkId: payment.check.check_id, checked: false });
  const accountantAck =
    ackState.checkId === payment.check.check_id ? ackState.checked : false;

  const setAccountantAck = (checked: boolean) => {
    setAckState({ checkId: payment.check.check_id, checked });
  };

  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const [noteDialog, setNoteDialog] = useState<NoteDialogKind>(null);
  const [noteText, setNoteText] = useState("");
  const [dialogError, setDialogError] = useState<string | null>(null);

  const hasAnyAction =
    permissions.can_sign ||
    permissions.can_send_to_director ||
    permissions.can_postpone ||
    permissions.can_resume ||
    permissions.can_cancel ||
    permissions.can_edit ||
    permissions.can_decide;

  const blockReasonText = (() => {
    if (permissions.can_sign || !permissions.sign_block_code) return null;
    if (permissions.sign_block_code === "forbidden_role") return null;
    const map: Record<string, string> = t.prod.detail.blockCodes;
    return map[permissions.sign_block_code] ?? t.prod.detail.blockCodes.default;
  })();

  // Terminal status banners when no actions remain.
  if (payment.status === "signed" && !hasAnyAction) {
    return (
      <Card className="border-[#00AB75]/35 bg-[#E8F8F2]/60 py-0">
        <CardContent className="p-4 space-y-2 text-sm text-[#064A34]">
          <div className="flex items-center gap-2 font-semibold">
            <CheckCircle2 className="size-4 shrink-0 text-[var(--brand-text)]" />
            <span>{t.prod.detail.signedBannerTitle}</span>
          </div>
          {payment.signed_by && payment.signed_at && (
            <p className="text-xs text-[#064A34]/85">
              {interpolate(t.prod.detail.signedByLine, {
                user: payment.signed_by.full_name,
                date: formatDate(payment.signed_at),
              })}
            </p>
          )}
          {payment.accountant_ack && (
            <p className="text-xs text-[#064A34]/85">
              {t.prod.detail.signedBannerWithAck}
            </p>
          )}
        </CardContent>
      </Card>
    );
  }

  if (payment.status === "cancelled" && !hasAnyAction) {
    return (
      <Card className="bg-muted/50 py-0">
        <CardContent className="p-4 text-sm text-muted-foreground">
          <div className="flex items-center gap-2 font-semibold text-foreground">
            <Ban className="size-4 shrink-0" />
            <span>{t.prod.detail.cancelledBannerTitle}</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  // Analyst or read-only viewer with zero permitted actions.
  if (!hasAnyAction && !blockReasonText) {
    return null;
  }

  const handleSign = async () => {
    if (!permissions.can_sign || busyAction) return;
    if (permissions.sign_requires_ack && !accountantAck) return;

    setActionError(null);
    setBusyAction("sign");
    try {
      const updated = await signPayment(
        payment.id,
        {
          accountant_ack: permissions.sign_requires_ack ? accountantAck : false,
        },
        lang
      );
      onPaymentUpdated(updated);
      notifyProdApprovalsUpdated();
      notify.success(t.prod.detail.toastSigned);
    } catch (err) {
      if (err instanceof ApiError && err.code === "verdict_changed") {
        setAccountantAck(false);
        if (err.payment) {
          onVerdictChanged(err.payment, err.detail);
        } else {
          setActionError(err.detail);
          void onReloadPayment();
        }
        notify.warning(t.prod.detail.verdictChangedToast, err.detail);
      } else {
        const message = getProdErrorMessage(err);
        setActionError(message);
        notify.error(t.check.actionErrorTitle, message);
        void onReloadPayment();
      }
    } finally {
      setBusyAction(null);
    }
  };

  const handleResume = async () => {
    if (!permissions.can_resume || busyAction) return;
    setActionError(null);
    setBusyAction("resume");
    try {
      const updated = await resumePayment(payment.id, lang);
      onPaymentUpdated(updated);
      notify.success(t.prod.detail.toastResumed);
    } catch (err) {
      const message = getProdErrorMessage(err);
      setActionError(message);
      notify.error(t.check.actionErrorTitle, message);
      void onReloadPayment();
    } finally {
      setBusyAction(null);
    }
  };

  const openNoteDialog = (kind: Exclude<NoteDialogKind, null>) => {
    setNoteText("");
    setDialogError(null);
    setNoteDialog(kind);
  };

  const closeNoteDialog = (nextOpen: boolean) => {
    if (!nextOpen && busyAction) return;
    if (!nextOpen) {
      setNoteDialog(null);
      setDialogError(null);
    }
  };

  const handleConfirmNoteDialog = async () => {
    if (!noteDialog || busyAction) return;
    setDialogError(null);
    setBusyAction(noteDialog);
    try {
      const trimmed = noteText.trim();
      let updated: Payment;
      if (noteDialog === "send") {
        updated = await sendPaymentToDirector(payment.id, trimmed, lang);
        notifyProdApprovalsUpdated();
        notify.success(t.prod.detail.toastSentToDirector);
      } else if (noteDialog === "postpone") {
        updated = await postponePayment(payment.id, trimmed || undefined, lang);
        notify.warning(t.prod.detail.toastPostponed);
      } else {
        updated = await cancelPayment(payment.id, trimmed || undefined, lang);
        notifyProdApprovalsUpdated();
        notify.info(t.prod.detail.toastCancelled);
      }
      onPaymentUpdated(updated);
      setNoteDialog(null);
      setNoteText("");
    } catch (err) {
      const message = getProdErrorMessage(err);
      setDialogError(message);
      notify.error(t.check.actionErrorTitle, message);
      void onReloadPayment();
    } finally {
      setBusyAction(null);
    }
  };

  const isSignDisabled =
    busyAction !== null || (permissions.sign_requires_ack && !accountantAck);

  return (
    <>
      <Card className="min-w-0 py-0">
        <CardContent className="p-4 space-y-3.5">
          <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {t.check.actionsEyebrow}
          </div>

          {actionError && (
            <Alert
              variant="destructive"
              className="rounded-xl border-red-300 bg-red-50/90"
            >
              <AlertCircle className="size-4" />
              <AlertTitle>{t.check.actionErrorTitle}</AlertTitle>
              <AlertDescription className="break-words">
                {actionError}
              </AlertDescription>
            </Alert>
          )}

          {blockReasonText && (
            <div className="flex items-start gap-2.5 rounded-xl border border-amber-300/90 bg-amber-50/90 p-3 text-xs leading-relaxed text-amber-950">
              <Lock className="mt-0.5 size-4 shrink-0 text-amber-700" />
              <span className="break-words">{blockReasonText}</span>
            </div>
          )}

          {permissions.can_sign && (
            <div className="space-y-2.5">
              {permissions.sign_requires_ack && (
                <div className="flex min-h-11 items-start gap-2.5 rounded-xl border border-border bg-background/80 px-3 py-2.5">
                  <Checkbox
                    id={`prod-ack-${payment.id}`}
                    checked={accountantAck}
                    onCheckedChange={(checked) =>
                      setAccountantAck(Boolean(checked))
                    }
                    disabled={busyAction !== null}
                    className="mt-0.5"
                  />
                  <div className="min-w-0 flex-1 space-y-1">
                    <Label
                      htmlFor={`prod-ack-${payment.id}`}
                      className="cursor-pointer text-xs font-medium leading-snug text-foreground"
                    >
                      {t.check.accountantAckLabel}
                    </Label>
                    {!accountantAck && (
                      <p className="text-[11px] leading-snug text-muted-foreground">
                        {t.check.accountantAckRequiredHint}
                      </p>
                    )}
                  </div>
                </div>
              )}

              <Button
                type="button"
                size="lg"
                disabled={isSignDisabled}
                onClick={() => void handleSign()}
                className="min-h-11 w-full gap-2 rounded-xl font-semibold shadow-[0_2px_8px_rgba(0,171,117,0.22)]"
              >
                {busyAction === "sign" ? (
                  <>
                    <Loader2 className="size-4 animate-spin" />
                    <span>{t.prod.detail.actions.signing}</span>
                  </>
                ) : (
                  <>
                    <ShieldCheck className="size-4" />
                    <span>{t.check.actionSign}</span>
                  </>
                )}
              </Button>
            </div>
          )}

          {permissions.can_decide && onOpenDecide && (
            <Button
              type="button"
              size="lg"
              disabled={busyAction !== null}
              onClick={onOpenDecide}
              className="min-h-11 w-full gap-2 rounded-xl font-semibold"
            >
              <ClipboardCheck className="size-4" />
              <span>{t.prod.detail.actions.decide}</span>
            </Button>
          )}

          {permissions.can_send_to_director && (
            <Button
              type="button"
              variant={permissions.can_sign ? "outline" : "default"}
              size="lg"
              disabled={busyAction !== null}
              onClick={() => openNoteDialog("send")}
              className="min-h-11 w-full gap-2 rounded-xl"
            >
              <Send className="size-4" />
              <span>{t.check.actionSendToDirector}</span>
            </Button>
          )}

          {permissions.can_edit && (
            <Button
              type="button"
              variant="outline"
              size="lg"
              disabled={busyAction !== null}
              onClick={onOpenEdit}
              className="min-h-11 w-full gap-2 rounded-xl"
            >
              <FileEdit className="size-4" />
              <span>{t.prod.detail.actions.edit}</span>
            </Button>
          )}

          {permissions.can_resume && (
            <Button
              type="button"
              variant="default"
              size="lg"
              disabled={busyAction !== null}
              onClick={() => void handleResume()}
              className="min-h-11 w-full gap-2 rounded-xl"
            >
              {busyAction === "resume" ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  <span>{t.prod.detail.actions.resuming}</span>
                </>
              ) : (
                <>
                  <RotateCcw className="size-4" />
                  <span>{t.prod.detail.actions.resume}</span>
                </>
              )}
            </Button>
          )}

          {permissions.can_postpone && (
            <Button
              type="button"
              variant="outline"
              size="lg"
              disabled={busyAction !== null}
              onClick={() => openNoteDialog("postpone")}
              className="min-h-11 w-full gap-2 rounded-xl"
            >
              <PauseCircle className="size-4" />
              <span>{t.prod.detail.actions.postpone}</span>
            </Button>
          )}

          {permissions.can_cancel && (
            <Button
              type="button"
              variant="ghost"
              size="lg"
              disabled={busyAction !== null}
              onClick={() => openNoteDialog("cancel")}
              className="min-h-11 w-full gap-2 rounded-xl text-destructive hover:bg-destructive/10 hover:text-destructive"
            >
              <Ban className="size-4" />
              <span>{t.prod.detail.actions.cancelPayment}</span>
            </Button>
          )}
        </CardContent>
      </Card>

      <Dialog open={noteDialog !== null} onOpenChange={closeNoteDialog}>
        <DialogContent mobileSheet className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              {noteDialog === "send"
                ? t.check.dialogTitle
                : noteDialog === "postpone"
                  ? t.prod.detail.postponeDialogTitle
                  : t.prod.detail.cancelDialogTitle}
            </DialogTitle>
            <DialogDescription>
              {noteDialog === "send"
                ? t.check.dialogDescription
                : noteDialog === "postpone"
                  ? t.prod.detail.postponeDialogDescription
                  : t.prod.detail.cancelDialogDescription}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3">
            {dialogError && (
              <Alert
                variant="destructive"
                className="border-red-300 bg-red-50/90"
              >
                <AlertCircle className="size-4" />
                <AlertDescription className="break-words">
                  {dialogError}
                </AlertDescription>
              </Alert>
            )}

            <div className="space-y-1.5">
              <Label htmlFor="prod-action-note">
                {noteDialog === "send"
                  ? t.check.accountantNoteLabel
                  : t.prod.detail.noteLabel}
              </Label>
              <Textarea
                id="prod-action-note"
                rows={3}
                maxLength={1000}
                placeholder={
                  noteDialog === "send"
                    ? t.check.accountantNotePlaceholder
                    : t.prod.detail.notePlaceholder
                }
                value={noteText}
                onChange={(e) => setNoteText(e.target.value)}
                disabled={busyAction !== null}
                className="min-h-24"
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => closeNoteDialog(false)}
              disabled={busyAction !== null}
              className="min-h-11 w-full sm:min-h-10 sm:w-auto"
            >
              {t.common.cancel}
            </Button>
            <Button
              type="button"
              variant={noteDialog === "cancel" ? "destructive" : "default"}
              onClick={() => void handleConfirmNoteDialog()}
              disabled={busyAction !== null}
              className="min-h-11 w-full gap-2 sm:min-h-10 sm:w-auto"
            >
              {busyAction !== null ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  <span>
                    {noteDialog === "send"
                      ? t.check.sending
                      : noteDialog === "postpone"
                        ? t.prod.detail.actions.postponing
                        : t.prod.detail.actions.cancelling}
                  </span>
                </>
              ) : noteDialog === "send" ? (
                <>
                  <Send className="size-4" />
                  <span>{t.check.send}</span>
                </>
              ) : noteDialog === "postpone" ? (
                <span>{t.prod.detail.postponeConfirm}</span>
              ) : (
                <span>{t.prod.detail.cancelConfirm}</span>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
