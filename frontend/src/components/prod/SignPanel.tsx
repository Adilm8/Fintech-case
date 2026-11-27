"use client";

import { useState } from "react";
import { AlertCircle, Loader2 } from "lucide-react";
import { notifyProdNotificationsUpdated } from "@/components/prod/NotificationBell";
import { notifyProdApprovalsUpdated } from "@/components/prod/ProdShell";
import { SignatureBindingNote } from "@/components/prod/SignatureBindingNote";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
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
  cancelPayment,
  getProdErrorMessage,
  postponePayment,
  resumePayment,
  sendPaymentToDirector,
  signPayment,
} from "@/lib/prod/api";
import { signPaymentDocument, type SignerKind } from "@/lib/prod/ncalayer";
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
  const [lastSignOutcome, setLastSignOutcome] = useState<{
    paymentId: string;
    signer: SignerKind;
    simulated: boolean;
  } | null>(null);

  const [noteDialog, setNoteDialog] = useState<NoteDialogKind>(null);
  const [noteText, setNoteText] = useState("");
  const [dialogError, setDialogError] = useState<string | null>(null);

  const documentDigest = payment.document_digest?.trim() || null;
  const matchedSignOutcome =
    lastSignOutcome && lastSignOutcome.paymentId === payment.id
      ? lastSignOutcome
      : null;

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
    const signedModeNote = matchedSignOutcome
      ? matchedSignOutcome.simulated
        ? t.prod.detail.signatureBinding.modeSimulated
        : t.prod.detail.signatureBinding.modeNcaLayer
      : undefined;

    return (
      <div role="status" className="ui-notice ui-notice-ok space-y-1">
        <div className="text-sm font-semibold text-foreground">
          {t.prod.detail.signedBannerTitle}
        </div>
        {payment.signed_by && payment.signed_at && (
          <p className="text-xs text-muted-foreground tabular-nums">
            {interpolate(t.prod.detail.signedByLine, {
              user: payment.signed_by.full_name,
              date: formatDate(payment.signed_at),
            })}
          </p>
        )}
        {payment.accountant_ack && (
          <p className="text-xs text-muted-foreground">
            {t.prod.detail.signedBannerWithAck}
          </p>
        )}
        {documentDigest ? (
          <SignatureBindingNote
            documentDigest={documentDigest}
            checkId={payment.check.check_id}
            rulesetVersion={payment.check.ruleset_version ?? "—"}
            labels={t.prod.detail.signatureBinding}
            signerNote={signedModeNote}
            className="pt-1"
          />
        ) : (
          signedModeNote && (
            <p className="text-[11px] leading-snug text-muted-foreground">
              {signedModeNote}
            </p>
          )
        )}
      </div>
    );
  }

  if (payment.status === "cancelled" && !hasAnyAction) {
    return (
      <div role="status" className="ui-notice ui-notice-neutral">
        <div className="text-sm font-semibold text-foreground">
          {t.prod.detail.cancelledBannerTitle}
        </div>
      </div>
    );
  }

  // Analyst or read-only viewer with zero permitted actions.
  if (!hasAnyAction && !blockReasonText) {
    return null;
  }

  const handleSign = async () => {
    if (!permissions.can_sign || busyAction || !documentDigest) return;
    if (permissions.sign_requires_ack && !accountantAck) return;

    setActionError(null);
    setBusyAction("sign");
    try {
      const outcome = await signPaymentDocument(payment.id, documentDigest, {
        accountantAck: permissions.sign_requires_ack ? accountantAck : false,
        lang,
        post: (pid, body) => signPayment(pid, body, lang),
      });
      setLastSignOutcome({
        paymentId: payment.id,
        signer: outcome.signer,
        simulated: outcome.simulated,
      });
      onPaymentUpdated(outcome.payment);
      notifyProdApprovalsUpdated();
      notifyProdNotificationsUpdated();
      notify.success(
        t.prod.detail.toastSigned,
        outcome.simulated
          ? t.prod.detail.signatureBinding.modeSimulated
          : t.prod.detail.signatureBinding.modeNcaLayer
      );
    } catch (err) {
      notifyProdNotificationsUpdated();
      if (err instanceof ApiError && err.code === "verdict_changed") {
        setAccountantAck(false);
        if (err.payment) {
          onVerdictChanged(err.payment, err.detail);
        } else {
          setActionError(err.detail);
          void onReloadPayment();
        }
        notify.warning(t.prod.detail.verdictChangedToast, err.detail);
      } else if (err instanceof ApiError && err.code === "document_mismatch") {
        setAccountantAck(false);
        const message =
          err.detail || t.prod.detail.blockCodes.document_mismatch;
        setActionError(message);
        notify.warning(t.prod.detail.documentMismatchToast, message);
        void onReloadPayment();
      } else if (
        err instanceof ApiError &&
        err.code === "signature_verification_unavailable"
      ) {
        const message =
          err.detail ||
          t.prod.detail.blockCodes.signature_verification_unavailable;
        setActionError(message);
        notify.error(t.check.actionErrorTitle, message);
        void onReloadPayment();
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
    busyAction !== null ||
    !documentDigest ||
    (permissions.sign_requires_ack && !accountantAck);
  const decideIsPrimary = Boolean(
    permissions.can_decide && onOpenDecide && !permissions.can_sign
  );
  const sendIsPrimary =
    permissions.can_send_to_director &&
    !permissions.can_sign &&
    !(permissions.can_decide && onOpenDecide);
  const resumeIsPrimary =
    permissions.can_resume &&
    !permissions.can_sign &&
    !(permissions.can_decide && onOpenDecide) &&
    !permissions.can_send_to_director;

  return (
    <>
      <div className="ui-panel min-w-0 p-4 space-y-3">
        <div className="ui-label-meta">{t.check.actionsEyebrow}</div>

        {actionError && (
          <Alert variant="destructive">
            <AlertCircle className="size-4" />
            <AlertTitle>{t.check.actionErrorTitle}</AlertTitle>
            <AlertDescription className="break-words">
              {actionError}
            </AlertDescription>
          </Alert>
        )}

        {blockReasonText && (
          <div className="ui-notice ui-notice-warn text-xs leading-relaxed break-words">
            {blockReasonText}
          </div>
        )}

        {permissions.can_sign && (
          <div className="space-y-2.5">
            {permissions.sign_requires_ack && (
              <div className="ui-subpanel flex min-h-11 items-start gap-2.5">
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
              disabled={isSignDisabled}
              onClick={() => void handleSign()}
              className="min-h-11 w-full sm:min-h-9"
            >
              {busyAction === "sign" ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  <span>{t.prod.detail.actions.signing}</span>
                </>
              ) : (
                <span>{t.check.actionSign}</span>
              )}
            </Button>

            {documentDigest && (
              <SignatureBindingNote
                documentDigest={documentDigest}
                checkId={payment.check.check_id}
                rulesetVersion={payment.check.ruleset_version ?? "—"}
                labels={t.prod.detail.signatureBinding}
                signerNote={t.prod.detail.signatureBinding.modeHint}
              />
            )}
          </div>
        )}

        {permissions.can_decide && onOpenDecide && (
          <Button
            type="button"
            variant={decideIsPrimary ? "default" : "outline"}
            disabled={busyAction !== null}
            onClick={onOpenDecide}
            className="min-h-11 w-full sm:min-h-9"
          >
            {t.prod.detail.actions.decide}
          </Button>
        )}

        {permissions.can_send_to_director && (
          <Button
            type="button"
            variant={sendIsPrimary ? "default" : "outline"}
            disabled={busyAction !== null}
            onClick={() => openNoteDialog("send")}
            className="min-h-11 w-full sm:min-h-9"
          >
            {t.check.actionSendToDirector}
          </Button>
        )}

        {permissions.can_edit && (
          <Button
            type="button"
            variant="outline"
            disabled={busyAction !== null}
            onClick={onOpenEdit}
            className="min-h-11 w-full sm:min-h-9"
          >
            {t.prod.detail.actions.edit}
          </Button>
        )}

        {permissions.can_resume && (
          <Button
            type="button"
            variant={resumeIsPrimary ? "default" : "outline"}
            disabled={busyAction !== null}
            onClick={() => void handleResume()}
            className="min-h-11 w-full sm:min-h-9"
          >
            {busyAction === "resume" ? (
              <>
                <Loader2 className="size-4 animate-spin" />
                <span>{t.prod.detail.actions.resuming}</span>
              </>
            ) : (
              <span>{t.prod.detail.actions.resume}</span>
            )}
          </Button>
        )}

        {permissions.can_postpone && (
          <Button
            type="button"
            variant="outline"
            disabled={busyAction !== null}
            onClick={() => openNoteDialog("postpone")}
            className="min-h-11 w-full sm:min-h-9"
          >
            {t.prod.detail.actions.postpone}
          </Button>
        )}

        {permissions.can_cancel && (
          <Button
            type="button"
            variant="ghost"
            disabled={busyAction !== null}
            onClick={() => openNoteDialog("cancel")}
            className="min-h-11 w-full text-[var(--status-danger-text)] hover:bg-[#FEF2F2] hover:text-[var(--status-danger-text)] sm:min-h-9"
          >
            {t.prod.detail.actions.cancelPayment}
          </Button>
        )}
      </div>

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
              <Alert variant="destructive">
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
              className="min-h-11 w-full sm:min-h-9 sm:w-auto"
            >
              {t.common.cancel}
            </Button>
            <Button
              type="button"
              variant={noteDialog === "cancel" ? "destructive" : "default"}
              onClick={() => void handleConfirmNoteDialog()}
              disabled={busyAction !== null}
              className="min-h-11 w-full sm:min-h-9 sm:w-auto"
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
                <span>{t.check.send}</span>
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
