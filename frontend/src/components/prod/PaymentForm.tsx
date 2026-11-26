"use client";

import { useId, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, AlertTriangle, Loader2, SearchCheck } from "lucide-react";
import { InvoiceUpload } from "@/components/InvoiceUpload";
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
import { extractInvalidFieldMap, localizeBackendText } from "@/lib/format";
import {
  applyMappedInvoiceValues,
  mapInvoiceToFormValues,
  needsManualConfirmation,
  type InvoiceExtraction,
} from "@/lib/invoice";
import {
  ApiError,
  createPayment,
  extractFieldErrors,
  getProdErrorMessage,
  updatePayment,
} from "@/lib/prod/api";
import type { Payment, PaymentInput } from "@/lib/prod/types";
import { notify } from "@/lib/toast";
import type { ComparisonField } from "@/lib/types";
import { cn } from "cn";

interface PaymentFormProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mode?: "create" | "edit";
  payment?: Payment | null;
  onSaved?: (payment: Payment) => void;
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
  doc_number: string;
  doc_date: string;
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
  doc_number: "",
  doc_date: "",
};

function sanitizeDigits(value: string): string {
  return value.replace(/\s+/g, "").replace(/\D+/g, "");
}

function sanitizeCode(value: string): string {
  return value.replace(/\s+/g, "").toUpperCase();
}

function paymentToFormState(payment: Payment): FormState {
  return {
    recipient_name: payment.request.recipient_name,
    recipient_bin: sanitizeDigits(payment.request.recipient_bin),
    recipient_iik: sanitizeCode(payment.request.recipient_iik),
    recipient_bik: sanitizeCode(payment.request.recipient_bik),
    amount_kzt: String(payment.request.amount_kzt),
    purpose: payment.request.purpose,
    kbe: payment.request.kbe?.trim() ? sanitizeDigits(payment.request.kbe) : "",
    knp: payment.request.knp?.trim() ? sanitizeDigits(payment.request.knp) : "",
    doc_number: payment.doc_number ?? "",
    doc_date: payment.doc_date ?? "",
  };
}

export function PaymentForm({
  open,
  onOpenChange,
  mode = "create",
  payment,
  onSaved,
}: PaymentFormProps) {
  const router = useRouter();
  const { t, lang, formatMoney, interpolate } = useT();
  const isEditMode = mode === "edit" && Boolean(payment);

  const [form, setForm] = useState<FormState>(() =>
    isEditMode && payment ? paymentToFormState(payment) : EMPTY_FORM
  );
  const [editedFields, setEditedFields] = useState<Set<keyof FormState>>(
    () => new Set()
  );
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [invoiceResetKey, setInvoiceResetKey] = useState(0);
  const [invoiceRequiresConfirmation, setInvoiceRequiresConfirmation] =
    useState(false);
  const [invoiceConfirmed, setInvoiceConfirmed] = useState(false);
  const [isExtractingInvoice, setIsExtractingInvoice] = useState(false);
  const confirmHintId = useId();

  const isConfirmationBlocked =
    invoiceRequiresConfirmation && !invoiceConfirmed;

  const invalidFields: Partial<Record<ComparisonField, string[]>> =
    isEditMode && payment
      ? extractInvalidFieldMap(payment.check.verdict, payment.check.signals)
      : {};

  const getFieldError = (
    formField: keyof FormState,
    compField?: "bin" | "iik" | "bik"
  ): string | null => {
    if (fieldErrors[formField]) {
      return fieldErrors[formField];
    }
    if (compField && !editedFields.has(formField) && invalidFields[compField]) {
      return invalidFields[compField]!
        .map((msg) => localizeBackendText(msg, lang))
        .join(" ");
    }
    return null;
  };

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
    if (fieldErrors[field]) {
      setFieldErrors((prev) => {
        const copy = { ...prev };
        delete copy[field];
        return copy;
      });
    }
    if (invoiceConfirmed) {
      setInvoiceConfirmed(false);
    }
    if (formError) setFormError(null);
  };

  const handleInvoiceExtracted = (extraction: InvoiceExtraction) => {
    const mapped = mapInvoiceToFormValues(extraction);
    const { updatedKeys } = applyMappedInvoiceValues(EMPTY_FORM, mapped);

    if (updatedKeys.length > 0) {
      setForm((prev) => applyMappedInvoiceValues(prev, mapped).next);
      setEditedFields((prev) => {
        const next = new Set(prev);
        for (const key of updatedKeys) {
          next.add(key);
        }
        return next;
      });
      setFieldErrors((prev) => {
        if (Object.keys(prev).length === 0) return prev;
        const copy = { ...prev };
        for (const key of updatedKeys) {
          delete copy[key];
        }
        return copy;
      });
    }

    setInvoiceRequiresConfirmation(needsManualConfirmation(extraction));
    setInvoiceConfirmed(false);
    if (formError) setFormError(null);
  };

  const handleInvoiceClear = () => {
    setInvoiceRequiresConfirmation(false);
    setInvoiceConfirmed(false);
  };

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen && !isSubmitting) {
      setFormError(null);
      setFieldErrors({});
      if (isExtractingInvoice) {
        setIsExtractingInvoice(false);
        setInvoiceRequiresConfirmation(false);
        setInvoiceConfirmed(false);
        setInvoiceResetKey((k) => k + 1);
      }
    }
    onOpenChange(nextOpen);
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (isSubmitting || isExtractingInvoice || isConfirmationBlocked) {
      return;
    }
    setFormError(null);
    setFieldErrors({});

    const recipient_name = form.recipient_name.trim();
    const recipient_bin = sanitizeDigits(form.recipient_bin);
    const recipient_iik = sanitizeCode(form.recipient_iik);
    const recipient_bik = sanitizeCode(form.recipient_bik);
    const purpose = form.purpose.trim();
    const kbe = sanitizeDigits(form.kbe).slice(0, 2);
    const knp = sanitizeDigits(form.knp).slice(0, 3);
    const doc_number = form.doc_number.trim();
    const doc_date = form.doc_date.trim() || null;
    const parsedAmount = Number(
      form.amount_kzt.replace(/\s+/g, "").replace(",", ".")
    );

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
      setFieldErrors({ amount_kzt: t.queue.errInvalidAmount });
      setFormError(t.queue.errInvalidAmount);
      return;
    }

    const input: PaymentInput = {
      recipient_name,
      recipient_bin,
      recipient_iik,
      recipient_bik,
      amount_kzt: parsedAmount,
      purpose,
      ...(kbe ? { kbe } : {}),
      ...(knp ? { knp } : {}),
      ...(doc_number ? { doc_number } : {}),
      ...(doc_date ? { doc_date } : {}),
    };

    setIsSubmitting(true);
    try {
      const saved =
        isEditMode && payment
          ? await updatePayment(payment.id, input, lang)
          : await createPayment(input, lang);

      onOpenChange(false);
      onSaved?.(saved);

      const verdictLabel = t.verdicts[saved.check.verdict] ?? t.verdicts.grey;
      notify.success(
        isEditMode
          ? t.prod.payments.form.updatedToast
          : t.prod.payments.form.createdToast,
        interpolate(t.toast.paymentCheckedDescription, {
          recipient: saved.request.recipient_name,
          amount: formatMoney(saved.request.amount_kzt),
          verdict: verdictLabel,
        })
      );

      setInvoiceRequiresConfirmation(false);
      setInvoiceConfirmed(false);
      setInvoiceResetKey((k) => k + 1);

      if (!isEditMode) {
        setForm(EMPTY_FORM);
        router.push(`/payments/${saved.id}`);
      }
    } catch (err) {
      const extracted = extractFieldErrors(err);
      if (Object.keys(extracted).length > 0) {
        setFieldErrors(extracted);
      }
      const message = getProdErrorMessage(err);
      if (
        err instanceof ApiError &&
        err.status === 422 &&
        Object.keys(extracted).length > 0
      ) {
        setFormError(err.detail || t.errors.validationDefault);
      } else {
        setFormError(message);
        notify.error(t.toast.paymentCheckErrorTitle, message);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const nameErr = getFieldError("recipient_name");
  const binErr = getFieldError("recipient_bin", "bin");
  const bikErr = getFieldError("recipient_bik", "bik");
  const iikErr = getFieldError("recipient_iik", "iik");
  const amountErr = getFieldError("amount_kzt");
  const kbeErr = getFieldError("kbe");
  const knpErr = getFieldError("knp");
  const purposeErr = getFieldError("purpose");
  const docNumErr = getFieldError("doc_number");
  const docDateErr = getFieldError("doc_date");

  const errInputClass =
    "border-rose-500 bg-rose-50/60 text-rose-950 focus-visible:border-rose-600 focus-visible:ring-rose-500/25";

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent mobileSheet className="sm:max-w-lg">
        <div
          aria-hidden="true"
          className="mx-auto -mt-1 mb-1 h-1.5 w-10 rounded-full bg-border sm:hidden"
        />

        <DialogHeader>
          <DialogTitle className="text-lg">
            {isEditMode
              ? t.prod.payments.form.editTitle
              : t.prod.payments.form.createTitle}
          </DialogTitle>
          <DialogDescription>
            {isEditMode
              ? t.prod.payments.form.editDescription
              : t.prod.payments.form.createDescription}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="min-w-0 space-y-4">
          {formError && (
            <Alert variant="destructive" className="border-red-300 bg-red-50/90">
              <AlertCircle className="size-4" />
              <AlertDescription className="break-words">
                {formError}
              </AlertDescription>
            </Alert>
          )}

          <InvoiceUpload
            key={invoiceResetKey}
            disabled={isSubmitting}
            confirmed={invoiceConfirmed}
            onExtracted={handleInvoiceExtracted}
            onConfirmedChange={setInvoiceConfirmed}
            onClear={handleInvoiceClear}
            onLoadingChange={setIsExtractingInvoice}
          />

          <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2">
            <div className="min-w-0 space-y-1.5 sm:col-span-2">
              <Label
                htmlFor="prod_recipient_name"
                className={cn(nameErr && "text-rose-900")}
              >
                {t.queue.labelRecipientName}
              </Label>
              <Input
                id="prod_recipient_name"
                aria-invalid={Boolean(nameErr)}
                placeholder={t.queue.placeholderRecipientName}
                className={cn("h-11 sm:h-10", nameErr && errInputClass)}
                value={form.recipient_name}
                onChange={(e) => updateField("recipient_name", e.target.value)}
              />
              {nameErr && (
                <p className="text-xs font-medium text-rose-800 break-words">
                  {nameErr}
                </p>
              )}
            </div>

            <div className="min-w-0 space-y-1.5">
              <Label
                htmlFor="prod_recipient_bin"
                className={cn(binErr && "text-rose-900")}
              >
                {t.queue.labelBin}
              </Label>
              <Input
                id="prod_recipient_bin"
                inputMode="numeric"
                aria-invalid={Boolean(binErr)}
                placeholder={t.queue.placeholderBin}
                className={cn("h-11 font-mono sm:h-10", binErr && errInputClass)}
                value={form.recipient_bin}
                onChange={(e) => updateField("recipient_bin", e.target.value)}
              />
              {binErr && (
                <p className="text-xs font-medium text-rose-800 break-words">
                  {binErr}
                </p>
              )}
            </div>

            <div className="min-w-0 space-y-1.5">
              <Label
                htmlFor="prod_recipient_bik"
                className={cn(bikErr && "text-rose-900")}
              >
                {t.queue.labelBik}
              </Label>
              <Input
                id="prod_recipient_bik"
                aria-invalid={Boolean(bikErr)}
                placeholder={t.queue.placeholderBik}
                className={cn(
                  "h-11 font-mono uppercase sm:h-10",
                  bikErr && errInputClass
                )}
                value={form.recipient_bik}
                onChange={(e) => updateField("recipient_bik", e.target.value)}
              />
              {bikErr && (
                <p className="text-xs font-medium text-rose-800 break-words">
                  {bikErr}
                </p>
              )}
            </div>

            <div className="min-w-0 space-y-1.5 sm:col-span-2">
              <Label
                htmlFor="prod_recipient_iik"
                className={cn(iikErr && "text-rose-900")}
              >
                {t.queue.labelIik}
              </Label>
              <Input
                id="prod_recipient_iik"
                aria-invalid={Boolean(iikErr)}
                placeholder={t.queue.placeholderIik}
                className={cn(
                  "h-11 font-mono uppercase sm:h-10",
                  iikErr && errInputClass
                )}
                value={form.recipient_iik}
                onChange={(e) => updateField("recipient_iik", e.target.value)}
              />
              {iikErr && (
                <p className="text-xs font-medium text-rose-800 break-words">
                  {iikErr}
                </p>
              )}
            </div>

            <div className="min-w-0 space-y-1.5 sm:col-span-2">
              <Label
                htmlFor="prod_amount_kzt"
                className={cn(amountErr && "text-rose-900")}
              >
                {t.queue.labelAmount}
              </Label>
              <Input
                id="prod_amount_kzt"
                type="number"
                min="0.01"
                step="any"
                aria-invalid={Boolean(amountErr)}
                placeholder={t.queue.placeholderAmount}
                className={cn(
                  "h-11 tabular-nums sm:h-10",
                  amountErr && errInputClass
                )}
                value={form.amount_kzt}
                onChange={(e) => updateField("amount_kzt", e.target.value)}
              />
              {amountErr && (
                <p className="text-xs font-medium text-rose-800 break-words">
                  {amountErr}
                </p>
              )}
            </div>

            <div className="min-w-0 space-y-1.5">
              <Label
                htmlFor="prod_kbe"
                className={cn(kbeErr && "text-rose-900")}
              >
                {t.queue.labelKbe}
              </Label>
              <Input
                id="prod_kbe"
                inputMode="numeric"
                maxLength={2}
                aria-invalid={Boolean(kbeErr)}
                placeholder={t.queue.placeholderKbe}
                className={cn("h-11 font-mono sm:h-10", kbeErr && errInputClass)}
                value={form.kbe}
                onChange={(e) => updateField("kbe", e.target.value)}
              />
              {kbeErr && (
                <p className="text-xs font-medium text-rose-800 break-words">
                  {kbeErr}
                </p>
              )}
            </div>

            <div className="min-w-0 space-y-1.5">
              <Label
                htmlFor="prod_knp"
                className={cn(knpErr && "text-rose-900")}
              >
                {t.queue.labelKnp}
              </Label>
              <Input
                id="prod_knp"
                inputMode="numeric"
                maxLength={3}
                aria-invalid={Boolean(knpErr)}
                placeholder={t.queue.placeholderKnp}
                className={cn("h-11 font-mono sm:h-10", knpErr && errInputClass)}
                value={form.knp}
                onChange={(e) => updateField("knp", e.target.value)}
              />
              {knpErr && (
                <p className="text-xs font-medium text-rose-800 break-words">
                  {knpErr}
                </p>
              )}
            </div>

            <div className="min-w-0 space-y-1.5">
              <Label
                htmlFor="prod_doc_number"
                className={cn(docNumErr && "text-rose-900")}
              >
                {t.prod.payments.form.docNumberLabel}
              </Label>
              <Input
                id="prod_doc_number"
                aria-invalid={Boolean(docNumErr)}
                placeholder={t.prod.payments.form.docNumberPlaceholder}
                className={cn("h-11 sm:h-10", docNumErr && errInputClass)}
                value={form.doc_number}
                onChange={(e) => updateField("doc_number", e.target.value)}
              />
              {docNumErr && (
                <p className="text-xs font-medium text-rose-800 break-words">
                  {docNumErr}
                </p>
              )}
            </div>

            <div className="min-w-0 space-y-1.5">
              <Label
                htmlFor="prod_doc_date"
                className={cn(docDateErr && "text-rose-900")}
              >
                {t.prod.payments.form.docDateLabel}
              </Label>
              <Input
                id="prod_doc_date"
                type="date"
                aria-invalid={Boolean(docDateErr)}
                className={cn("h-11 sm:h-10", docDateErr && errInputClass)}
                value={form.doc_date}
                onChange={(e) => updateField("doc_date", e.target.value)}
              />
              {docDateErr && (
                <p className="text-xs font-medium text-rose-800 break-words">
                  {docDateErr}
                </p>
              )}
            </div>

            <div className="min-w-0 space-y-1.5 sm:col-span-2">
              <Label
                htmlFor="prod_purpose"
                className={cn(purposeErr && "text-rose-900")}
              >
                {t.queue.labelPurpose}
              </Label>
              <Input
                id="prod_purpose"
                aria-invalid={Boolean(purposeErr)}
                placeholder={t.queue.placeholderPurpose}
                className={cn("h-11 sm:h-10", purposeErr && errInputClass)}
                value={form.purpose}
                onChange={(e) => updateField("purpose", e.target.value)}
              />
              {purposeErr && (
                <p className="text-xs font-medium text-rose-800 break-words">
                  {purposeErr}
                </p>
              )}
            </div>
          </div>

          {isConfirmationBlocked && (
            <p
              id={confirmHintId}
              role="status"
              className="flex items-start gap-2 rounded-xl border border-amber-300/90 bg-amber-50/90 px-3 py-2 text-xs font-medium text-amber-950 dark:border-amber-700/60 dark:bg-amber-950/40 dark:text-amber-100"
            >
              <AlertTriangle
                aria-hidden="true"
                className="mt-0.5 size-4 shrink-0 text-amber-700 dark:text-amber-400"
              />
              <span className="min-w-0 flex-1 break-words">
                {t.invoice.submitBlockedHint}
              </span>
            </p>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={isSubmitting}
              className="min-h-11 w-full sm:min-h-10 sm:w-auto"
            >
              {t.common.cancel}
            </Button>
            <Button
              type="submit"
              disabled={
                isSubmitting || isExtractingInvoice || isConfirmationBlocked
              }
              aria-describedby={
                isConfirmationBlocked ? confirmHintId : undefined
              }
              className="min-h-11 w-full gap-2 sm:min-h-10 sm:w-auto"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="size-4 animate-spin motion-reduce:animate-none" />
                  <span>
                    {isEditMode
                      ? t.prod.payments.form.saving
                      : t.prod.payments.form.creating}
                  </span>
                </>
              ) : (
                <>
                  <SearchCheck className="size-4" />
                  <span>
                    {isEditMode
                      ? t.prod.payments.form.submitSave
                      : t.prod.payments.form.submitCreate}
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
