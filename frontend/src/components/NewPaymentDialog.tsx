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
import { localizeBackendText } from "@/lib/format";
import { notify } from "@/lib/toast";
import type { CheckRequest, CheckResult, ComparisonField } from "@/lib/types";
import { cn } from "cn";

interface NewPaymentDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mode?: "create" | "edit";
  prefillRequest?: CheckRequest | null;
  invalidFields?: Partial<Record<ComparisonField, string[]>>;
  onPaymentCreated: (
    request: CheckRequest,
    result: CheckResult
  ) => string | void;
  onOpenPaymentCheck?: (
    id: string,
    request: CheckRequest,
    result: CheckResult
  ) => void;
  onNetworkError: (message: string) => void;
}

interface FormState {
  recipient_name: string;
  recipient_bin: string;
  recipient_iik: string;
  recipient_bik: string;
  amount_kzt: string;
  purpose: string;
  kbe: string;
  knp: string;
}

const DEFAULT_KBE = "17";
const DEFAULT_KNP = "710";

const EMPTY_FORM: FormState = {
  recipient_name: "",
  recipient_bin: "",
  recipient_iik: "",
  recipient_bik: "",
  amount_kzt: "",
  purpose: "",
  kbe: DEFAULT_KBE,
  knp: DEFAULT_KNP,
};

function sanitizeDigits(value: string): string {
  return value.replace(/\s+/g, "").replace(/\D+/g, "");
}

function sanitizeCode(value: string): string {
  return value.replace(/\s+/g, "").toUpperCase();
}

function requestToFormState(req: CheckRequest): FormState {
  return {
    recipient_name: req.recipient_name,
    recipient_bin: sanitizeDigits(req.recipient_bin),
    recipient_iik: sanitizeCode(req.recipient_iik),
    recipient_bik: sanitizeCode(req.recipient_bik),
    amount_kzt: String(req.amount_kzt),
    purpose: req.purpose,
    kbe: req.kbe?.trim() ? sanitizeDigits(req.kbe) : DEFAULT_KBE,
    knp: req.knp?.trim() ? sanitizeDigits(req.knp) : DEFAULT_KNP,
  };
}

export function NewPaymentDialog({
  open,
  onOpenChange,
  mode = "create",
  prefillRequest,
  invalidFields,
  onPaymentCreated,
  onOpenPaymentCheck,
  onNetworkError,
}: NewPaymentDialogProps) {
  const { t, lang, formatMoney, interpolate } = useT();
  const isEditMode = mode === "edit";

  const [form, setForm] = useState<FormState>(() =>
    prefillRequest ? requestToFormState(prefillRequest) : EMPTY_FORM
  );
  const [editedFields, setEditedFields] = useState<Set<keyof FormState>>(
    () => new Set()
  );
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const getFieldInvalidReasons = (
    compField: "bin" | "iik" | "bik",
    formField: keyof FormState
  ): string[] => {
    if (editedFields.has(formField)) return [];
    const reasons = invalidFields?.[compField];
    if (!reasons) return [];
    return reasons.map((msg) => localizeBackendText(msg, lang));
  };

  const binInvalidReasons = getFieldInvalidReasons("bin", "recipient_bin");
  const bikInvalidReasons = getFieldInvalidReasons("bik", "recipient_bik");
  const iikInvalidReasons = getFieldInvalidReasons("iik", "recipient_iik");
  const isBinInvalid =
    !editedFields.has("recipient_bin") && Boolean(invalidFields?.bin);
  const isBikInvalid =
    !editedFields.has("recipient_bik") && Boolean(invalidFields?.bik);
  const isIikInvalid =
    !editedFields.has("recipient_iik") && Boolean(invalidFields?.iik);

  const updateField = (field: keyof FormState, rawValue: string) => {
    let value = rawValue;
    if (field === "recipient_bin") {
      value = sanitizeDigits(rawValue);
    } else if (field === "kbe") {
      value = sanitizeDigits(rawValue).slice(0, 2);
    } else if (field === "knp") {
      value = sanitizeDigits(rawValue).slice(0, 3);
    } else if (field === "recipient_iik" || field === "recipient_bik") {
      value = sanitizeCode(rawValue);
    }
    setForm((prev) => ({ ...prev, [field]: value }));
    setEditedFields((prev) => {
      if (prev.has(field)) return prev;
      const next = new Set(prev);
      next.add(field);
      return next;
    });
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
    const recipient_bin = sanitizeDigits(form.recipient_bin);
    const recipient_iik = sanitizeCode(form.recipient_iik);
    const recipient_bik = sanitizeCode(form.recipient_bik);
    const purpose = form.purpose.trim();
    const kbe = sanitizeDigits(form.kbe).slice(0, 2);
    const knp = sanitizeDigits(form.knp).slice(0, 3);
    const parsedAmount = Number(
      form.amount_kzt.replace(/\s+/g, "").replace(",", ".")
    );

    setForm((prev) => ({
      ...prev,
      recipient_bin,
      recipient_iik,
      recipient_bik,
      kbe,
      knp,
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
      ...(kbe ? { kbe } : {}),
      ...(knp ? { knp } : {}),
    };

    setIsSubmitting(true);
    try {
      const result = await checkPayment(payload, lang);
      if (!isEditMode) {
        setForm(EMPTY_FORM);
      }
      setFormError(null);
      onOpenChange(false);
      const itemId = onPaymentCreated(payload, result);

      const verdictLabel = t.verdicts[result.verdict] ?? t.verdicts.grey;
      const toastTitle = isEditMode
        ? t.toast.paymentFixedTitle
        : t.toast.paymentCheckedTitle;
      const toastDescription = interpolate(t.toast.paymentCheckedDescription, {
        recipient: payload.recipient_name,
        amount: formatMoney(payload.amount_kzt),
        verdict: verdictLabel,
      });

      notify.success(toastTitle, {
        description: toastDescription,
        ...(onOpenPaymentCheck && typeof itemId === "string"
          ? {
              action: {
                label: t.toast.openCheckAction,
                onClick: () => onOpenPaymentCheck(itemId, payload, result),
              },
            }
          : {}),
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
            {isEditMode ? t.queue.fixPaymentTitle : t.queue.newPaymentTitle}
          </DialogTitle>
          <DialogDescription>
            {isEditMode
              ? t.queue.fixPaymentDescription
              : t.queue.newPaymentDescription}
          </DialogDescription>
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
              <Label
                htmlFor="dialog_recipient_bin"
                className={cn(isBinInvalid && "text-rose-900")}
              >
                {t.queue.labelBin}
              </Label>
              <Input
                id="dialog_recipient_bin"
                inputMode="numeric"
                aria-invalid={isBinInvalid}
                placeholder={t.queue.placeholderBin}
                className={cn(
                  "h-11 font-mono sm:h-10",
                  isBinInvalid &&
                    "border-rose-500 bg-rose-50/60 text-rose-950 focus-visible:border-rose-600 focus-visible:ring-rose-500/25"
                )}
                value={form.recipient_bin}
                onChange={(e) => updateField("recipient_bin", e.target.value)}
              />
              {isBinInvalid && binInvalidReasons.length > 0 && (
                <p className="text-xs font-medium text-rose-800 break-words">
                  {binInvalidReasons.join(" ")}
                </p>
              )}
            </div>

            <div className="min-w-0 space-y-1.5">
              <Label
                htmlFor="dialog_recipient_bik"
                className={cn(isBikInvalid && "text-rose-900")}
              >
                {t.queue.labelBik}
              </Label>
              <Input
                id="dialog_recipient_bik"
                aria-invalid={isBikInvalid}
                placeholder={t.queue.placeholderBik}
                className={cn(
                  "h-11 font-mono uppercase sm:h-10",
                  isBikInvalid &&
                    "border-rose-500 bg-rose-50/60 text-rose-950 focus-visible:border-rose-600 focus-visible:ring-rose-500/25"
                )}
                value={form.recipient_bik}
                onChange={(e) => updateField("recipient_bik", e.target.value)}
              />
              {isBikInvalid && bikInvalidReasons.length > 0 && (
                <p className="text-xs font-medium text-rose-800 break-words">
                  {bikInvalidReasons.join(" ")}
                </p>
              )}
            </div>

            <div className="min-w-0 space-y-1.5 sm:col-span-2">
              <Label
                htmlFor="dialog_recipient_iik"
                className={cn(isIikInvalid && "text-rose-900")}
              >
                {t.queue.labelIik}
              </Label>
              <Input
                id="dialog_recipient_iik"
                aria-invalid={isIikInvalid}
                placeholder={t.queue.placeholderIik}
                className={cn(
                  "h-11 font-mono uppercase sm:h-10",
                  isIikInvalid &&
                    "border-rose-500 bg-rose-50/60 text-rose-950 focus-visible:border-rose-600 focus-visible:ring-rose-500/25"
                )}
                value={form.recipient_iik}
                onChange={(e) => updateField("recipient_iik", e.target.value)}
              />
              {isIikInvalid && iikInvalidReasons.length > 0 && (
                <p className="text-xs font-medium text-rose-800 break-words">
                  {iikInvalidReasons.join(" ")}
                </p>
              )}
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

            <div className="min-w-0 space-y-1.5">
              <Label htmlFor="dialog_kbe">{t.queue.labelKbe}</Label>
              <Input
                id="dialog_kbe"
                inputMode="numeric"
                maxLength={2}
                placeholder={t.queue.placeholderKbe}
                className="h-11 font-mono sm:h-10"
                value={form.kbe}
                onChange={(e) => updateField("kbe", e.target.value)}
              />
            </div>

            <div className="min-w-0 space-y-1.5">
              <Label htmlFor="dialog_knp">{t.queue.labelKnp}</Label>
              <Input
                id="dialog_knp"
                inputMode="numeric"
                maxLength={3}
                placeholder={t.queue.placeholderKnp}
                className="h-11 font-mono sm:h-10"
                value={form.knp}
                onChange={(e) => updateField("knp", e.target.value)}
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
                  <span>
                    {isEditMode
                      ? t.queue.submitFixCheck
                      : t.queue.submitCheck}
                  </span>
                </>
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
