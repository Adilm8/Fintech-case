"use client";

import { useState, type FormEvent } from "react";
import { AlertCircle, Loader2, SearchCheck } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useT } from "@/i18n";
import {
  checkPayment,
  getErrorMessage,
  isNetworkUnreachableError,
} from "@/lib/api";
import { notify } from "@/lib/toast";
import type { CheckRequest, CheckResult } from "@/lib/types";

interface NewPaymentDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  prefillRequest?: CheckRequest | null;
  onPaymentCreated: (request: CheckRequest, result: CheckResult) => void;
  onOpenPaymentCheck: (request: CheckRequest, result: CheckResult) => void;
  onNetworkError: (message: string) => void;
}

interface FormState {
  recipient_name: string;
  recipient_bin: string;
  recipient_iik: string;
  recipient_bik: string;
  amount_kzt: string;
  purpose: string;
}

const EMPTY_FORM: FormState = {
  recipient_name: "",
  recipient_bin: "",
  recipient_iik: "",
  recipient_bik: "",
  amount_kzt: "",
  purpose: "",
};

function sanitizeBin(value: string): string {
  return value.replace(/\s+/g, "").replace(/\D+/g, "");
}

function sanitizeCode(value: string): string {
  return value.replace(/\s+/g, "").toUpperCase();
}

function requestToFormState(req: CheckRequest): FormState {
  return {
    recipient_name: req.recipient_name,
    recipient_bin: sanitizeBin(req.recipient_bin),
    recipient_iik: sanitizeCode(req.recipient_iik),
    recipient_bik: sanitizeCode(req.recipient_bik),
    amount_kzt: String(req.amount_kzt),
    purpose: req.purpose,
  };
}

export function NewPaymentDialog({
  open,
  onOpenChange,
  prefillRequest,
  onPaymentCreated,
  onOpenPaymentCheck,
  onNetworkError,
}: NewPaymentDialogProps) {
  const { t, lang, formatMoney, interpolate } = useT();

  const [form, setForm] = useState<FormState>(() =>
    prefillRequest ? requestToFormState(prefillRequest) : EMPTY_FORM
  );
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const updateField = (field: keyof FormState, rawValue: string) => {
    let value = rawValue;
    if (field === "recipient_bin") {
      value = sanitizeBin(rawValue);
    } else if (field === "recipient_iik" || field === "recipient_bik") {
      value = sanitizeCode(rawValue);
    }
    setForm((prev) => ({ ...prev, [field]: value }));
    if (formError) setFormError(null);
  };

  const handleClose = (nextOpen: boolean) => {
    if (!nextOpen && !isSubmitting) {
      setFormError(null);
    }
    onOpenChange(nextOpen);
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setFormError(null);

    const recipient_name = form.recipient_name.trim();
    const recipient_bin = sanitizeBin(form.recipient_bin);
    const recipient_iik = sanitizeCode(form.recipient_iik);
    const recipient_bik = sanitizeCode(form.recipient_bik);
    const purpose = form.purpose.trim();
    const parsedAmount = Number(
      form.amount_kzt.replace(/\s+/g, "").replace(",", ".")
    );

    setForm((prev) => ({
      ...prev,
      recipient_bin,
      recipient_iik,
      recipient_bik,
    }));

    if (
      !recipient_name ||
      !recipient_bin ||
      !recipient_iik ||
      !recipient_bik ||
      !purpose
    ) {
      setFormError(t.queue.errFillAll);
      return;
    }

    if (!Number.isFinite(parsedAmount) || parsedAmount <= 0) {
      setFormError(t.queue.errInvalidAmount);
      return;
    }

    const payload: CheckRequest = {
      ...(prefillRequest?.payer_id !== undefined
        ? { payer_id: prefillRequest.payer_id }
        : {}),
      recipient_name,
      recipient_bin,
      recipient_iik,
      recipient_bik,
      amount_kzt: parsedAmount,
      purpose,
    };

    setIsSubmitting(true);
    try {
      const result = await checkPayment(payload, lang);
      setForm(EMPTY_FORM);
      setFormError(null);
      onOpenChange(false);
      onPaymentCreated(payload, result);

      const verdictLabel = t.verdicts[result.verdict] ?? t.verdicts.grey;
      notify.success(t.toast.paymentCheckedTitle, {
        description: interpolate(t.toast.paymentCheckedDescription, {
          recipient: payload.recipient_name,
          amount: formatMoney(payload.amount_kzt),
          verdict: verdictLabel,
        }),
        action: {
          label: t.toast.openCheckAction,
          onClick: () => onOpenPaymentCheck(payload, result),
        },
      });
    } catch (err) {
      const message = getErrorMessage(err);
      if (isNetworkUnreachableError(err)) {
        onNetworkError(message);
        notify.error(t.common.serverErrorTitle, message);
      } else {
        setFormError(message);
        notify.error(t.toast.paymentCheckErrorTitle, message);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent mobileSheet className="sm:max-w-lg">
        <div
          aria-hidden="true"
          className="mx-auto -mt-1 mb-1 h-1.5 w-10 rounded-full bg-border sm:hidden"
        />

        <DialogHeader>
          <DialogTitle className="text-lg">
            {t.queue.newPaymentTitle}
          </DialogTitle>
          <DialogDescription>{t.queue.newPaymentDescription}</DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          {formError && (
            <Alert variant="destructive" className="bg-red-50/90 border-red-300">
              <AlertCircle className="size-4" />
              <AlertDescription className="break-words">
                {formError}
              </AlertDescription>
            </Alert>
          )}

          <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2">
            <div className="min-w-0 space-y-1.5 sm:col-span-2">
              <Label htmlFor="dialog_recipient_name">
                {t.queue.labelRecipientName}
              </Label>
              <Input
                id="dialog_recipient_name"
                placeholder={t.queue.placeholderRecipientName}
                className="h-11 sm:h-10"
                value={form.recipient_name}
                onChange={(e) => updateField("recipient_name", e.target.value)}
              />
            </div>

            <div className="min-w-0 space-y-1.5">
              <Label htmlFor="dialog_recipient_bin">{t.queue.labelBin}</Label>
              <Input
                id="dialog_recipient_bin"
                inputMode="numeric"
                placeholder={t.queue.placeholderBin}
                className="h-11 font-mono sm:h-10"
                value={form.recipient_bin}
                onChange={(e) => updateField("recipient_bin", e.target.value)}
              />
            </div>

            <div className="min-w-0 space-y-1.5">
              <Label htmlFor="dialog_recipient_bik">{t.queue.labelBik}</Label>
              <Input
                id="dialog_recipient_bik"
                placeholder={t.queue.placeholderBik}
                className="h-11 font-mono uppercase sm:h-10"
                value={form.recipient_bik}
                onChange={(e) => updateField("recipient_bik", e.target.value)}
              />
            </div>

            <div className="min-w-0 space-y-1.5 sm:col-span-2">
              <Label htmlFor="dialog_recipient_iik">{t.queue.labelIik}</Label>
              <Input
                id="dialog_recipient_iik"
                placeholder={t.queue.placeholderIik}
                className="h-11 font-mono uppercase sm:h-10"
                value={form.recipient_iik}
                onChange={(e) => updateField("recipient_iik", e.target.value)}
              />
            </div>

            <div className="min-w-0 space-y-1.5 sm:col-span-2">
              <Label htmlFor="dialog_amount_kzt">{t.queue.labelAmount}</Label>
              <Input
                id="dialog_amount_kzt"
                type="number"
                min="1"
                step="any"
                placeholder={t.queue.placeholderAmount}
                className="h-11 tabular-nums sm:h-10"
                value={form.amount_kzt}
                onChange={(e) => updateField("amount_kzt", e.target.value)}
              />
            </div>

            <div className="min-w-0 space-y-1.5 sm:col-span-2">
              <Label htmlFor="dialog_purpose">{t.queue.labelPurpose}</Label>
              <Input
                id="dialog_purpose"
                placeholder={t.queue.placeholderPurpose}
                className="h-11 sm:h-10"
                value={form.purpose}
                onChange={(e) => updateField("purpose", e.target.value)}
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => handleClose(false)}
              disabled={isSubmitting}
              className="min-h-11 w-full sm:min-h-10 sm:w-auto"
            >
              {t.common.cancel}
            </Button>
            <Button
              type="submit"
              disabled={isSubmitting}
              className="min-h-11 w-full gap-2 sm:min-h-10 sm:w-auto"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  <span>{t.queue.submitChecking}</span>
                </>
              ) : (
                <>
                  <SearchCheck className="size-4" />
                  <span>{t.queue.submitCheck}</span>
                </>
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
