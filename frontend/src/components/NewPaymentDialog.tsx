"use client";

import {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { Loader2 } from "lucide-react";
import { InvoiceUpload } from "@/components/InvoiceUpload";
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
import { Skeleton } from "@/components/ui/skeleton";
import { useT } from "@/i18n";
import {
  checkPayment,
  getErrorMessage,
  getFieldErrors,
  getHistory,
  isNetworkUnreachableError,
} from "@/lib/api";
import { getBankByBik, getBankFromIik } from "@/lib/banks";
import { localizeBackendText } from "@/lib/format";
import {
  applyMappedInvoiceValues,
  mapInvoiceToFormValues,
  needsManualConfirmation,
  type InvoiceExtraction,
  type InvoiceMappedFormValues,
} from "@/lib/invoice";
import {
  filterSupplierSuggestions,
  findSupplierByBin,
  findSupplierByName,
  groupHistoryBySupplier,
  type SupplierSuggestion,
} from "@/lib/suppliers";
import { notify } from "@/lib/toast";
import type { CheckRequest, CheckResult, ComparisonField } from "@/lib/types";
import {
  formatAmountInput,
  formatIikGrouped,
  formatNumberToAmountInput,
  parseAmountInput,
  stripNonDigits,
  stripSpacesUpper,
  validateBinLive,
  validateIikLive,
} from "@/lib/validators";
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

type FieldOrigin = "empty" | "history" | "user" | "invoice" | "auto_from_iik";

interface InvoiceHistoryConflict {
  supplier: SupplierSuggestion;
  invoiceIik: string;
  invoiceBik: string;
  choice: "unresolved" | "invoice" | "history";
}

const DEFAULT_KBE = "17";
const DEFAULT_KNP = "710";

const LATIN_LOOKALIKE_TO_CYRILLIC: Record<string, string> = {
  a: "а",
  b: "в",
  c: "с",
  e: "е",
  h: "н",
  i: "і",
  k: "к",
  m: "м",
  o: "о",
  p: "р",
  t: "т",
  x: "х",
  y: "у",
};

function foldLookalikeName(value: string): string {
  return value
    .toLowerCase()
    .replace(/[«»"'`„“”]/g, " ")
    .replace(/[abcehikmoptxy]/g, (ch) => LATIN_LOOKALIKE_TO_CYRILLIC[ch] ?? ch)
    .replace(/ё/g, "е")
    .replace(/\s+/g, " ")
    .trim();
}

function findSupplierByConfusableName(
  suppliers: SupplierSuggestion[],
  rawName: string | null | undefined
): SupplierSuggestion | null {
  if (!rawName) return null;
  const target = foldLookalikeName(rawName);
  if (!target) return null;
  return (
    suppliers.find((s) =>
      s.aliases.some((alias) => foldLookalikeName(alias) === target)
    ) ?? null
  );
}

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

function requestToFormState(
  req: CheckRequest,
  decimalSep: "," | "."
): FormState {
  return {
    recipient_name: req.recipient_name,
    recipient_bin: stripNonDigits(req.recipient_bin).slice(0, 12),
    recipient_iik: formatIikGrouped(req.recipient_iik),
    recipient_bik: stripSpacesUpper(req.recipient_bik),
    amount_kzt: formatNumberToAmountInput(req.amount_kzt, decimalSep),
    purpose: req.purpose,
    kbe: req.kbe?.trim() ? stripNonDigits(req.kbe).slice(0, 2) : DEFAULT_KBE,
    knp: req.knp?.trim() ? stripNonDigits(req.knp).slice(0, 3) : DEFAULT_KNP,
  };
}

function countNonSpacesBefore(value: string, cursor: number): number {
  let count = 0;
  for (let i = 0; i < Math.min(cursor, value.length); i += 1) {
    if (!/\s/.test(value[i])) count += 1;
  }
  return count;
}

function findCursorForNonSpaces(formatted: string, targetCount: number): number {
  if (targetCount <= 0) return 0;
  let seen = 0;
  for (let i = 0; i < formatted.length; i += 1) {
    if (!/\s/.test(formatted[i])) {
      seen += 1;
      if (seen >= targetCount) {
        return i + 1;
      }
    }
  }
  return formatted.length;
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
  const { t, lang, formatMoney, formatDate, interpolate } = useT();
  const isEditMode = mode === "edit";
  const decimalSep: "," | "." = lang === "en" ? "." : ",";

  const [form, setForm] = useState<FormState>(() =>
    prefillRequest ? requestToFormState(prefillRequest, decimalSep) : EMPTY_FORM
  );
  const [editedFields, setEditedFields] = useState<Set<keyof FormState>>(
    () => new Set()
  );
  const [iikOrigin, setIikOrigin] = useState<FieldOrigin>(() =>
    prefillRequest?.recipient_iik ? "user" : "empty"
  );
  const [bikOrigin, setBikOrigin] = useState<FieldOrigin>(() =>
    prefillRequest?.recipient_bik ? "user" : "empty"
  );

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [serverFieldErrors, setServerFieldErrors] = useState<
    Record<string, string>
  >({});

  const [invoiceResetKey, setInvoiceResetKey] = useState(0);
  const [invoiceRequiresConfirmation, setInvoiceRequiresConfirmation] =
    useState(false);
  const [invoiceConfirmed, setInvoiceConfirmed] = useState(false);
  const [isExtractingInvoice, setIsExtractingInvoice] = useState(false);
  const [invoiceConflict, setInvoiceConflict] =
    useState<InvoiceHistoryConflict | null>(null);

  const [suppliers, setSuppliers] = useState<SupplierSuggestion[]>([]);
  const [isLoadingSuppliers, setIsLoadingSuppliers] = useState(false);
  const [selectedSupplier, setSelectedSupplier] =
    useState<SupplierSuggestion | null>(null);
  const [activeSuggestField, setActiveSuggestField] = useState<
    "name" | "bin" | null
  >(null);
  const [highlightedSuggestIdx, setHighlightedSuggestIdx] = useState(0);

  const confirmHintId = useId();
  const conflictHintId = useId();
  const suggestListId = useId();

  const iikInputRef = useRef<HTMLInputElement>(null);
  const amountInputRef = useRef<HTMLInputElement>(null);
  const nameInputRef = useRef<HTMLInputElement>(null);
  const binInputRef = useRef<HTMLInputElement>(null);
  const bikInputRef = useRef<HTMLInputElement>(null);
  const purposeInputRef = useRef<HTMLInputElement>(null);
  const kbeInputRef = useRef<HTMLInputElement>(null);
  const knpInputRef = useRef<HTMLInputElement>(null);
  const pendingInvoiceRef = useRef<InvoiceMappedFormValues | null>(null);
  const selectedSupplierRef = useRef<SupplierSuggestion | null>(null);
  const formRef = useRef<FormState>(form);

  useEffect(() => {
    selectedSupplierRef.current = selectedSupplier;
  }, [selectedSupplier]);

  useEffect(() => {
    formRef.current = form;
  }, [form]);

  const evaluateInvoiceConflict = (
    mapped: InvoiceMappedFormValues,
    supplierList: SupplierSuggestion[],
    currentForm: FormState,
    prevSelected: SupplierSuggestion | null
  ): InvoiceHistoryConflict | null => {
    const candidateBin = mapped.recipient_bin ?? currentForm.recipient_bin;
    const candidateName = mapped.recipient_name ?? currentForm.recipient_name;
    const historyMatch =
      findSupplierByBin(supplierList, candidateBin) ??
      findSupplierByName(supplierList, candidateName) ??
      findSupplierByConfusableName(supplierList, candidateName) ??
      prevSelected;

    if (!historyMatch) return null;

    const invoiceIik = stripSpacesUpper(mapped.recipient_iik ?? "");
    const invoiceBik =
      stripSpacesUpper(mapped.recipient_bik ?? "") ||
      (invoiceIik ? getBankFromIik(invoiceIik)?.bik ?? "" : "");

    const iikConflicts =
      Boolean(invoiceIik) &&
      Boolean(historyMatch.lastIik) &&
      invoiceIik !== historyMatch.lastIik;
    const bikConflicts =
      Boolean(invoiceBik) &&
      Boolean(historyMatch.lastBik) &&
      invoiceBik !== historyMatch.lastBik;

    if (!iikConflicts && !bikConflicts) {
      return null;
    }

    return {
      supplier: historyMatch,
      invoiceIik: invoiceIik || historyMatch.lastIik,
      invoiceBik: invoiceBik || historyMatch.lastBik,
      choice: "unresolved",
    };
  };

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    let active = true;

    const loadSuppliers = async () => {
      setIsLoadingSuppliers(true);
      try {
        const entries = await getHistory(lang, { signal: controller.signal });
        if (!active) return;
        const grouped = groupHistoryBySupplier(entries);
        setSuppliers(grouped);
        if (pendingInvoiceRef.current) {
          const conflict = evaluateInvoiceConflict(
            pendingInvoiceRef.current,
            grouped,
            formRef.current,
            selectedSupplierRef.current
          );
          if (conflict) {
            setInvoiceConflict((prev) => prev ?? conflict);
          }
          pendingInvoiceRef.current = null;
        }
      } catch {
        // Autocomplete degrades gracefully if history endpoint is unreachable.
      } finally {
        if (active) {
          setIsLoadingSuppliers(false);
        }
      }
    };

    void loadSuppliers();
    return () => {
      active = false;
      controller.abort();
    };
  }, [open, lang]);

  const matchedSupplier = useMemo(() => {
    const byBin = findSupplierByBin(suppliers, form.recipient_bin);
    if (byBin) return byBin;
    if (selectedSupplier) {
      const currentDigits = stripNonDigits(form.recipient_bin);
      if (!currentDigits || currentDigits === selectedSupplier.bin) {
        return selectedSupplier;
      }
    }
    return null;
  }, [suppliers, form.recipient_bin, selectedSupplier]);

  const suggestQuery =
    activeSuggestField === "bin"
      ? form.recipient_bin
      : activeSuggestField === "name"
        ? form.recipient_name
        : "";

  const filteredSuggestions = useMemo(() => {
    if (!activeSuggestField) return [];
    return filterSupplierSuggestions(suppliers, suggestQuery, 6);
  }, [activeSuggestField, suppliers, suggestQuery]);

  const showSuggestionsDropdown =
    activeSuggestField !== null &&
    (isLoadingSuppliers || filteredSuggestions.length > 0);

  const iikValidation = useMemo(
    () => validateIikLive(form.recipient_iik),
    [form.recipient_iik]
  );

  const binValidation = useMemo(
    () => validateBinLive(form.recipient_bin),
    [form.recipient_bin]
  );

  const cleanIik = iikValidation.clean;
  const cleanBik = stripSpacesUpper(form.recipient_bik);

  const detectedBank = iikValidation.bank;
  const bikMatchesDetectedBank =
    !detectedBank || !cleanBik || cleanBik === detectedBank.bik;
  const bikBankInfo = useMemo(() => getBankByBik(cleanBik), [cleanBik]);

  const iikDiffersFromHistory =
    Boolean(matchedSupplier?.lastIik) &&
    Boolean(cleanIik) &&
    cleanIik !== matchedSupplier?.lastIik;

  const bikDiffersFromHistory =
    Boolean(matchedSupplier?.lastBik) &&
    Boolean(cleanBik) &&
    cleanBik !== matchedSupplier?.lastBik;

  const isConfirmationBlocked =
    invoiceRequiresConfirmation && !invoiceConfirmed;
  const isConflictBlocked = invoiceConflict?.choice === "unresolved";

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

  const isBinServerInvalid =
    Boolean(serverFieldErrors.recipient_bin) ||
    (!editedFields.has("recipient_bin") && Boolean(invalidFields?.bin));
  const isBikServerInvalid =
    Boolean(serverFieldErrors.recipient_bik) ||
    (!editedFields.has("recipient_bik") && Boolean(invalidFields?.bik));
  const isIikServerInvalid =
    Boolean(serverFieldErrors.recipient_iik) ||
    (!editedFields.has("recipient_iik") && Boolean(invalidFields?.iik));

  const isBinInvalid = isBinServerInvalid || binValidation.status === "invalid";
  const isIikInvalid = isIikServerInvalid || iikValidation.status === "invalid";
  const isBikInvalid = isBikServerInvalid;

  const clearFieldServerError = (field: keyof FormState) => {
    if (serverFieldErrors[field]) {
      setServerFieldErrors((prev) => {
        const next = { ...prev };
        delete next[field];
        return next;
      });
    }
  };

  const markEdited = (field: keyof FormState) => {
    setEditedFields((prev) => {
      if (prev.has(field)) return prev;
      const next = new Set(prev);
      next.add(field);
      return next;
    });
  };

  const updateField = (
    field: keyof FormState,
    rawValue: string,
    selectionStart?: number | null
  ) => {
    let value = rawValue;

    if (field === "recipient_bin") {
      value = stripNonDigits(rawValue).slice(0, 12);
      setHighlightedSuggestIdx(0);
    } else if (field === "recipient_name") {
      setHighlightedSuggestIdx(0);
    } else if (field === "kbe") {
      value = stripNonDigits(rawValue).slice(0, 2);
    } else if (field === "knp") {
      value = stripNonDigits(rawValue).slice(0, 3);
    } else if (field === "recipient_bik") {
      value = stripSpacesUpper(rawValue).slice(0, 11);
      setBikOrigin(value ? "user" : "empty");
      if (invoiceConflict?.choice === "unresolved") {
        setInvoiceConflict(null);
      }
    } else if (field === "recipient_iik") {
      const nonSpacesBefore =
        typeof selectionStart === "number"
          ? countNonSpacesBefore(rawValue, selectionStart)
          : null;
      value = formatIikGrouped(rawValue);
      setIikOrigin(value ? "user" : "empty");
      if (invoiceConflict?.choice === "unresolved") {
        setInvoiceConflict(null);
      }
      if (nonSpacesBefore !== null) {
        window.requestAnimationFrame(() => {
          const el = iikInputRef.current;
          if (el && document.activeElement === el) {
            const pos = findCursorForNonSpaces(value, nonSpacesBefore);
            el.setSelectionRange(pos, pos);
          }
        });
      }
    } else if (field === "amount_kzt") {
      const nonSpacesBefore =
        typeof selectionStart === "number"
          ? countNonSpacesBefore(rawValue, selectionStart)
          : null;
      value = formatAmountInput(rawValue, decimalSep);
      if (nonSpacesBefore !== null) {
        window.requestAnimationFrame(() => {
          const el = amountInputRef.current;
          if (el && document.activeElement === el) {
            const pos = findCursorForNonSpaces(value, nonSpacesBefore);
            el.setSelectionRange(pos, pos);
          }
        });
      }
    }

    setForm((prev) => {
      const next = { ...prev, [field]: value };
      // Auto-fill BIK from IIK bank code ONLY when BIK field is currently empty.
      if (field === "recipient_iik" && !prev.recipient_bik.trim()) {
        const bank = getBankFromIik(value);
        if (bank) {
          next.recipient_bik = bank.bik;
          setBikOrigin("auto_from_iik");
        }
      }
      return next;
    });

    markEdited(field);
    clearFieldServerError(field);
    if (invoiceConfirmed) {
      setInvoiceConfirmed(false);
    }
    if (formError) setFormError(null);
  };

  const handleSelectSupplier = (supplier: SupplierSuggestion) => {
    setSelectedSupplier(supplier);
    setActiveSuggestField(null);
    setHighlightedSuggestIdx(0);

    const currentIikClean = stripSpacesUpper(form.recipient_iik);
    const currentBikClean = stripSpacesUpper(form.recipient_bik);

    // Safety: NEVER silently overwrite user-entered or invoice-extracted IIK/BIK.
    const canFillIik = !currentIikClean || iikOrigin === "history";
    const canFillBik =
      !currentBikClean ||
      bikOrigin === "history" ||
      bikOrigin === "auto_from_iik";

    const hasInvoiceConflict =
      (iikOrigin === "invoice" &&
        Boolean(currentIikClean) &&
        currentIikClean !== supplier.lastIik) ||
      (bikOrigin === "invoice" &&
        Boolean(currentBikClean) &&
        currentBikClean !== supplier.lastBik);

    setForm((prev) => ({
      ...prev,
      recipient_name: supplier.name,
      recipient_bin: supplier.bin,
      recipient_iik: canFillIik
        ? formatIikGrouped(supplier.lastIik)
        : prev.recipient_iik,
      recipient_bik: canFillBik ? supplier.lastBik : prev.recipient_bik,
    }));

    if (canFillIik && supplier.lastIik) {
      setIikOrigin("history");
    }
    if (canFillBik && supplier.lastBik) {
      setBikOrigin("history");
    }

    if (hasInvoiceConflict) {
      setInvoiceConflict({
        supplier,
        invoiceIik: currentIikClean || supplier.lastIik,
        invoiceBik: currentBikClean || supplier.lastBik,
        choice: "unresolved",
      });
    } else {
      setInvoiceConflict(null);
    }

    setEditedFields((prev) => {
      const next = new Set(prev);
      next.add("recipient_name");
      next.add("recipient_bin");
      if (canFillIik) next.add("recipient_iik");
      if (canFillBik) next.add("recipient_bik");
      return next;
    });

    setServerFieldErrors((prev) => {
      const next = { ...prev };
      delete next.recipient_name;
      delete next.recipient_bin;
      if (canFillIik) delete next.recipient_iik;
      if (canFillBik) delete next.recipient_bik;
      return next;
    });

    if (formError) setFormError(null);
  };

  const handleSuggestKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (!showSuggestionsDropdown) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (filteredSuggestions.length > 0) {
        setHighlightedSuggestIdx((prev) => (prev + 1) % filteredSuggestions.length);
      }
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (filteredSuggestions.length > 0) {
        setHighlightedSuggestIdx(
          (prev) =>
            (prev - 1 + filteredSuggestions.length) % filteredSuggestions.length
        );
      }
    } else if (e.key === "Enter" && filteredSuggestions.length > 0) {
      e.preventDefault();
      const chosen =
        filteredSuggestions[
          Math.min(highlightedSuggestIdx, filteredSuggestions.length - 1)
        ];
      if (chosen) {
        handleSelectSupplier(chosen);
      }
    } else if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      setActiveSuggestField(null);
    }
  };

  const handleInvoiceExtracted = (extraction: InvoiceExtraction) => {
    const mapped = mapInvoiceToFormValues(extraction);
    const formattedMapped: InvoiceMappedFormValues = { ...mapped };
    if (mapped.recipient_iik) {
      formattedMapped.recipient_iik = formatIikGrouped(mapped.recipient_iik);
    }
    if (mapped.recipient_bin) {
      formattedMapped.recipient_bin = stripNonDigits(mapped.recipient_bin).slice(
        0,
        12
      );
    }
    if (mapped.amount_kzt) {
      formattedMapped.amount_kzt = formatAmountInput(
        mapped.amount_kzt,
        decimalSep
      );
    }

    const { next: nextForm, updatedKeys } = applyMappedInvoiceValues(
      form,
      formattedMapped
    );

    // If invoice provided IIK without BIK and BIK is empty, auto-detect BIK from IIK code.
    if (
      formattedMapped.recipient_iik &&
      !formattedMapped.recipient_bik &&
      !nextForm.recipient_bik.trim()
    ) {
      const bank = getBankFromIik(formattedMapped.recipient_iik);
      if (bank) {
        nextForm.recipient_bik = bank.bik;
        setBikOrigin("auto_from_iik");
      }
    }

    if (updatedKeys.length > 0) {
      setForm(nextForm);
      setEditedFields((prev) => {
        const next = new Set(prev);
        for (const key of updatedKeys) {
          next.add(key);
        }
        return next;
      });
      setServerFieldErrors((prev) => {
        const next = { ...prev };
        for (const key of updatedKeys) {
          delete next[key];
        }
        return next;
      });
    }

    if (mapped.recipient_iik) setIikOrigin("invoice");
    if (mapped.recipient_bik) setBikOrigin("invoice");

    // Check conflict against supplier history — never silently overwrite invoice values!
    if (suppliers.length > 0) {
      const conflict = evaluateInvoiceConflict(
        mapped,
        suppliers,
        nextForm,
        selectedSupplier
      );
      setInvoiceConflict(conflict);
      pendingInvoiceRef.current = null;
    } else {
      pendingInvoiceRef.current = mapped;
      setInvoiceConflict(null);
    }

    setInvoiceRequiresConfirmation(needsManualConfirmation(extraction));
    setInvoiceConfirmed(false);
    setActiveSuggestField(null);
    if (formError) setFormError(null);
  };

  const handleInvoiceClear = () => {
    setInvoiceRequiresConfirmation(false);
    setInvoiceConfirmed(false);
    setInvoiceConflict(null);
    pendingInvoiceRef.current = null;
  };

  const handleResolveConflict = (choice: "invoice" | "history") => {
    if (!invoiceConflict) return;
    if (choice === "invoice") {
      setForm((prev) => ({
        ...prev,
        recipient_iik: formatIikGrouped(invoiceConflict.invoiceIik),
        recipient_bik: invoiceConflict.invoiceBik,
      }));
      setIikOrigin("invoice");
      setBikOrigin("invoice");
    } else {
      setForm((prev) => ({
        ...prev,
        recipient_iik: formatIikGrouped(invoiceConflict.supplier.lastIik),
        recipient_bik: invoiceConflict.supplier.lastBik,
      }));
      setIikOrigin("history");
      setBikOrigin("history");
    }
    setInvoiceConflict((prev) => (prev ? { ...prev, choice } : null));
    clearFieldServerError("recipient_iik");
    clearFieldServerError("recipient_bik");
    if (formError) setFormError(null);
  };

  const handleApplyDetectedBik = () => {
    if (!detectedBank) return;
    setForm((prev) => ({ ...prev, recipient_bik: detectedBank.bik }));
    setBikOrigin("user");
    markEdited("recipient_bik");
    clearFieldServerError("recipient_bik");
  };

  const handleClose = (nextOpen: boolean) => {
    if (!nextOpen && !isSubmitting) {
      setFormError(null);
      setServerFieldErrors({});
      setActiveSuggestField(null);
      if (isExtractingInvoice) {
        setIsExtractingInvoice(false);
        setInvoiceRequiresConfirmation(false);
        setInvoiceConfirmed(false);
        setInvoiceConflict(null);
        setInvoiceResetKey((k) => k + 1);
      }
    }
    onOpenChange(nextOpen);
  };

  const focusFirstErrorField = (fieldErrors: Record<string, string>) => {
    const fieldOrder: Array<[keyof FormState, React.RefObject<HTMLInputElement | null>]> = [
      ["recipient_name", nameInputRef],
      ["recipient_bin", binInputRef],
      ["recipient_bik", bikInputRef],
      ["recipient_iik", iikInputRef],
      ["amount_kzt", amountInputRef],
      ["kbe", kbeInputRef],
      ["knp", knpInputRef],
      ["purpose", purposeInputRef],
    ];
    for (const [key, ref] of fieldOrder) {
      if (fieldErrors[key] && ref.current) {
        ref.current.focus();
        break;
      }
    }
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (
      isSubmitting ||
      isExtractingInvoice ||
      isConfirmationBlocked ||
      isConflictBlocked
    ) {
      return;
    }
    setFormError(null);
    setServerFieldErrors({});
    setActiveSuggestField(null);

    const recipient_name = form.recipient_name.trim();
    const recipient_bin = stripNonDigits(form.recipient_bin);
    const recipient_iik = stripSpacesUpper(form.recipient_iik);
    const recipient_bik = stripSpacesUpper(form.recipient_bik);
    const purpose = form.purpose.trim();
    const kbe = stripNonDigits(form.kbe).slice(0, 2);
    const knp = stripNonDigits(form.knp).slice(0, 3);
    const parsedAmount = parseAmountInput(form.amount_kzt);

    const localErrors: Record<string, string> = {};
    if (!recipient_name) localErrors.recipient_name = t.errors.validationName;
    if (!recipient_bin) localErrors.recipient_bin = t.errors.validationBin;
    if (!recipient_iik) localErrors.recipient_iik = t.errors.validationIik;
    if (!recipient_bik) localErrors.recipient_bik = t.errors.validationBik;
    if (!purpose) localErrors.purpose = t.queue.errFillAll;

    if (Object.keys(localErrors).length > 0) {
      setServerFieldErrors(localErrors);
      setFormError(t.queue.errFillAll);
      focusFirstErrorField(localErrors);
      return;
    }

    if (!Number.isFinite(parsedAmount) || parsedAmount <= 0) {
      const amountErrors = { amount_kzt: t.queue.errInvalidAmount };
      setServerFieldErrors(amountErrors);
      setFormError(t.queue.errInvalidAmount);
      focusFirstErrorField(amountErrors);
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
      const result = await checkPayment(payload, lang, {
        historyAction: isEditMode ? "recheck" : "check",
      });
      if (!isEditMode) {
        setForm(EMPTY_FORM);
        setSelectedSupplier(null);
        setIikOrigin("empty");
        setBikOrigin("empty");
      }
      setInvoiceRequiresConfirmation(false);
      setInvoiceConfirmed(false);
      setInvoiceConflict(null);
      pendingInvoiceRef.current = null;
      setInvoiceResetKey((k) => k + 1);
      setFormError(null);
      setServerFieldErrors({});
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
      const fieldErrors = getFieldErrors(err);
      if (isNetworkUnreachableError(err)) {
        onNetworkError(message);
        notify.error(t.common.serverErrorTitle, message);
      } else {
        if (Object.keys(fieldErrors).length > 0) {
          setServerFieldErrors(fieldErrors);
          focusFirstErrorField(fieldErrors);
        }
        setFormError(message);
        notify.error(t.toast.paymentCheckErrorTitle, message);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const getIikStatusMessage = (): string | null => {
    switch (iikValidation.code) {
      case "idle":
        return null;
      case "valid":
        return t.queue.iikValid;
      case "incomplete":
        return interpolate(t.queue.iikIncomplete, {
          count: iikValidation.length,
        });
      case "cyrillic":
        return t.queue.iikErrCyrillic;
      case "prefix_kz":
        return t.queue.iikErrPrefix;
      case "alnum":
        return t.queue.iikErrAlnum;
      case "length":
        return interpolate(t.queue.iikErrLength, {
          count: iikValidation.length,
        });
      case "check_digits":
        return t.queue.iikErrCheckDigits;
      case "checksum":
        return t.queue.iikErrChecksum;
      case "bank_code_digits":
        return t.queue.iikErrBankCodeDigits;
      case "unknown_bank_code":
        return interpolate(t.queue.iikErrUnknownBank, {
          code: iikValidation.bankCode ?? "",
        });
    }
  };

  const getBinStatusMessage = (): string | null => {
    switch (binValidation.code) {
      case "idle":
        return null;
      case "valid":
        return t.queue.binValid;
      case "incomplete":
        return interpolate(t.queue.binIncomplete, {
          count: binValidation.length,
        });
      case "all_zeros":
        return t.queue.binErrAllZeros;
      case "invalid_month":
        return t.queue.binErrMonth;
      case "invalid_fifth":
        return t.queue.binErrFifth;
      case "checksum":
        return t.queue.binErrChecksum;
    }
  };

  const binEntityLabel =
    binValidation.entityType &&
    binValidation.entityType !== "invalid_fifth"
      ? t.queue.entityTypes[binValidation.entityType]
      : null;

  const iikStatusMessage = getIikStatusMessage();
  const binStatusMessage = getBinStatusMessage();

  const renderSuggestionsListbox = () => {
    if (!showSuggestionsDropdown) return null;

    return (
      <div
        id={suggestListId}
        role="listbox"
        aria-label={t.queue.supplierSuggestionsTitle}
        className="absolute top-full left-0 right-0 z-30 mt-1 max-h-64 overflow-y-auto rounded-[6px] border border-border bg-card p-1 shadow-[var(--shadow-overlay)]"
      >
        <div className="ui-label-meta px-2 py-1">
          {t.queue.supplierSuggestionsTitle}
        </div>

        {isLoadingSuppliers && filteredSuggestions.length === 0 ? (
          <div className="space-y-1.5 p-1">
            {Array.from({ length: 3 }).map((_, idx) => (
              <div
                key={`sup-skel-${idx}`}
                className="space-y-1.5 rounded-[4px] border border-border p-2"
              >
                <Skeleton className="h-4 w-44 rounded-[4px]" />
                <Skeleton className="h-3 w-64 rounded-[4px]" />
              </div>
            ))}
          </div>
        ) : (
          <div className="space-y-0.5">
            {filteredSuggestions.map((supplier, idx) => {
              const isHighlighted = idx === highlightedSuggestIdx;
              return (
                <button
                  key={supplier.bin}
                  type="button"
                  role="option"
                  aria-selected={isHighlighted}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    handleSelectSupplier(supplier);
                  }}
                  onMouseEnter={() => setHighlightedSuggestIdx(idx)}
                  className={cn(
                    "w-full cursor-pointer rounded-[4px] px-2.5 py-2 text-left transition-colors",
                    isHighlighted
                      ? "bg-muted text-foreground"
                      : "text-foreground hover:bg-muted/60"
                  )}
                >
                  <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-0.5">
                    <span className="text-sm font-medium leading-snug break-words">
                      {supplier.name}
                    </span>
                    <span className="font-mono text-xs tabular-nums text-muted-foreground">
                      {interpolate(t.common.binPrefix, { bin: supplier.bin })}
                    </span>
                  </div>
                  <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted-foreground">
                    <span className="font-mono tabular-nums text-[var(--text-secondary)] break-all">
                      {formatIikGrouped(supplier.lastIik)}
                    </span>
                    {supplier.bankName && (
                      <>
                        <span aria-hidden="true">·</span>
                        <span className="max-w-[210px] truncate">
                          {supplier.bankName}
                        </span>
                      </>
                    )}
                  </div>
                  <div className="mt-0.5 flex flex-wrap items-center gap-x-2.5 gap-y-0.5 text-[11px] tabular-nums text-muted-foreground">
                    {supplier.lastPaidAt && (
                      <span>
                        {interpolate(t.queue.supplierLastPaid, {
                          date: formatDate(supplier.lastPaidAt),
                        })}
                      </span>
                    )}
                    {supplier.typicalAmountKzt !== null && (
                      <span className="font-medium text-[var(--text-secondary)]">
                        {interpolate(t.queue.supplierTypicalAmount, {
                          amount: formatMoney(supplier.typicalAmountKzt),
                        })}
                      </span>
                    )}
                    <span>
                      {interpolate(t.queue.supplierPaymentsCount, {
                        count: supplier.paymentsCount,
                      })}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>
    );
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent mobileSheet className="sm:max-w-xl">
        <div
          aria-hidden="true"
          className="mx-auto -mt-1 mb-1 h-1 w-10 rounded-full bg-border sm:hidden"
        />

        <DialogHeader>
          <DialogTitle>
            {isEditMode ? t.queue.fixPaymentTitle : t.queue.newPaymentTitle}
          </DialogTitle>
          <DialogDescription>
            {isEditMode
              ? t.queue.fixPaymentDescription
              : t.queue.newPaymentDescription}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="min-w-0 space-y-4">
          {formError && (
            <div
              role="alert"
              className="ui-notice ui-notice-danger py-2 text-xs text-foreground break-words"
            >
              {formError}
            </div>
          )}

          <InvoiceUpload
            key={invoiceResetKey}
            disabled={isSubmitting}
            showDemoSample={isEditMode ? false : undefined}
            confirmed={invoiceConfirmed}
            onExtracted={handleInvoiceExtracted}
            onConfirmedChange={setInvoiceConfirmed}
            onClear={handleInvoiceClear}
            onLoadingChange={setIsExtractingInvoice}
          />

          {/* Explicit conflict choice when uploaded invoice differs from payment history */}
          {invoiceConflict && (
            <div
              role="region"
              aria-live="polite"
              className={cn(
                "ui-notice min-w-0 space-y-3",
                invoiceConflict.choice === "unresolved"
                  ? "ui-notice-warn"
                  : "ui-notice-neutral"
              )}
            >
              <div className="min-w-0 space-y-0.5">
                <div className="text-sm font-semibold leading-snug text-foreground">
                  {t.queue.invoiceConflictTitle}
                </div>
                <p className="text-xs leading-5 text-muted-foreground break-words">
                  {interpolate(t.queue.invoiceConflictDescription, {
                    supplier: invoiceConflict.supplier.name,
                    bin: invoiceConflict.supplier.bin,
                  })}
                </p>
              </div>

              <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
                <div
                  className={cn(
                    "min-w-0 space-y-2 rounded-[6px] border bg-card p-2.5",
                    invoiceConflict.choice === "invoice"
                      ? "border-foreground"
                      : "border-border"
                  )}
                >
                  <div className="ui-label-meta">
                    {t.queue.invoiceConflictInvoiceLabel}
                  </div>
                  <div className="space-y-0.5 font-mono text-xs tabular-nums text-foreground">
                    <div className="font-semibold break-all">
                      {formatIikGrouped(invoiceConflict.invoiceIik)}
                    </div>
                    <div className="text-muted-foreground">
                      {invoiceConflict.invoiceBik}
                      {getBankByBik(invoiceConflict.invoiceBik)?.name
                        ? ` · ${getBankByBik(invoiceConflict.invoiceBik)?.name}`
                        : ""}
                    </div>
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    variant={
                      invoiceConflict.choice === "invoice"
                        ? "default"
                        : "outline"
                    }
                    onClick={() => handleResolveConflict("invoice")}
                    className="min-h-9 w-full text-xs sm:min-h-8"
                  >
                    {t.queue.invoiceConflictUseInvoice}
                  </Button>
                </div>

                <div
                  className={cn(
                    "min-w-0 space-y-2 rounded-[6px] border bg-card p-2.5",
                    invoiceConflict.choice === "history"
                      ? "border-foreground"
                      : "border-border"
                  )}
                >
                  <div className="ui-label-meta">
                    {invoiceConflict.supplier.lastPaidAt
                      ? interpolate(t.queue.invoiceConflictHistoryLabel, {
                          date: formatDate(invoiceConflict.supplier.lastPaidAt),
                        })
                      : t.queue.invoiceConflictHistoryNoDate}
                  </div>
                  <div className="space-y-0.5 font-mono text-xs tabular-nums text-foreground">
                    <div className="font-semibold break-all">
                      {formatIikGrouped(invoiceConflict.supplier.lastIik)}
                    </div>
                    <div className="text-muted-foreground">
                      {invoiceConflict.supplier.lastBik}
                      {invoiceConflict.supplier.bankName
                        ? ` · ${invoiceConflict.supplier.bankName}`
                        : ""}
                    </div>
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    variant={
                      invoiceConflict.choice === "history"
                        ? "default"
                        : "outline"
                    }
                    onClick={() => handleResolveConflict("history")}
                    className="min-h-9 w-full text-xs sm:min-h-8"
                  >
                    {t.queue.invoiceConflictUseHistory}
                  </Button>
                </div>
              </div>

              {invoiceConflict.choice !== "unresolved" && (
                <p className="text-xs font-medium text-muted-foreground">
                  {invoiceConflict.choice === "invoice"
                    ? t.queue.invoiceConflictSelectedInvoice
                    : t.queue.invoiceConflictSelectedHistory}
                </p>
              )}
            </div>
          )}

          <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2">
            {/* Recipient Name with supplier autocomplete */}
            <div className="relative min-w-0 space-y-1.5 sm:col-span-2">
              <Label htmlFor="dialog_recipient_name">
                {t.queue.labelRecipientName}
              </Label>
              <Input
                ref={nameInputRef}
                id="dialog_recipient_name"
                role="combobox"
                aria-expanded={
                  activeSuggestField === "name" && showSuggestionsDropdown
                }
                aria-controls={
                  activeSuggestField === "name" ? suggestListId : undefined
                }
                aria-autocomplete="list"
                aria-invalid={Boolean(serverFieldErrors.recipient_name)}
                autoComplete="off"
                placeholder={t.queue.placeholderRecipientName}
                className="h-10 bg-card sm:h-9"
                value={form.recipient_name}
                onFocus={() => {
                  if (!isEditMode) {
                    setActiveSuggestField("name");
                    setHighlightedSuggestIdx(0);
                  }
                }}
                onBlur={() => {
                  setActiveSuggestField((prev) =>
                    prev === "name" ? null : prev
                  );
                }}
                onKeyDown={handleSuggestKeyDown}
                onChange={(e) => {
                  if (!isEditMode && activeSuggestField !== "name") {
                    setActiveSuggestField("name");
                  }
                  updateField("recipient_name", e.target.value);
                }}
              />
              {activeSuggestField === "name" && renderSuggestionsListbox()}
              {serverFieldErrors.recipient_name && (
                <p className="text-xs font-medium text-[var(--status-danger-text)] break-words">
                  {serverFieldErrors.recipient_name}
                </p>
              )}
            </div>

            {/* BIN / IIN with live checksum & entity type tag + autocomplete */}
            <div className="relative min-w-0 space-y-1.5">
              <div className="flex flex-wrap items-center justify-between gap-1.5">
                <Label htmlFor="dialog_recipient_bin">
                  {t.queue.labelBin}
                </Label>
                {binEntityLabel && (
                  <span className="ui-tag">{binEntityLabel}</span>
                )}
              </div>
              <Input
                ref={binInputRef}
                id="dialog_recipient_bin"
                role="combobox"
                aria-expanded={
                  activeSuggestField === "bin" && showSuggestionsDropdown
                }
                aria-controls={
                  activeSuggestField === "bin" ? suggestListId : undefined
                }
                aria-autocomplete="list"
                autoComplete="off"
                inputMode="numeric"
                maxLength={12}
                aria-invalid={isBinInvalid}
                placeholder={t.queue.placeholderBin}
                className="h-10 bg-card font-mono tabular-nums sm:h-9"
                value={form.recipient_bin}
                onFocus={() => {
                  if (!isEditMode && form.recipient_bin.trim().length > 0) {
                    setActiveSuggestField("bin");
                    setHighlightedSuggestIdx(0);
                  }
                }}
                onBlur={() => {
                  setActiveSuggestField((prev) =>
                    prev === "bin" ? null : prev
                  );
                }}
                onKeyDown={handleSuggestKeyDown}
                onChange={(e) => {
                  if (!isEditMode) {
                    setActiveSuggestField("bin");
                  }
                  updateField("recipient_bin", e.target.value);
                }}
              />
              {activeSuggestField === "bin" && renderSuggestionsListbox()}

              {serverFieldErrors.recipient_bin ? (
                <p className="text-xs font-medium text-[var(--status-danger-text)] break-words">
                  {serverFieldErrors.recipient_bin}
                </p>
              ) : binInvalidReasons.length > 0 ? (
                <p className="text-xs font-medium text-[var(--status-danger-text)] break-words">
                  {binInvalidReasons.join(" ")}
                </p>
              ) : binStatusMessage ? (
                <p
                  className={cn(
                    "text-xs break-words",
                    binValidation.status === "valid"
                      ? "font-medium text-[var(--status-ok-text)]"
                      : binValidation.status === "invalid"
                        ? "font-medium text-[var(--status-danger-text)]"
                        : "text-muted-foreground"
                  )}
                >
                  {binStatusMessage}
                </p>
              ) : null}
            </div>

            {/* BIK with bank name & IIK bank code mismatch warning */}
            <div className="min-w-0 space-y-1.5">
              <Label htmlFor="dialog_recipient_bik">
                {t.queue.labelBik}
              </Label>
              <Input
                ref={bikInputRef}
                id="dialog_recipient_bik"
                aria-invalid={isBikInvalid}
                placeholder={t.queue.placeholderBik}
                className="h-10 bg-card font-mono uppercase tabular-nums sm:h-9"
                value={form.recipient_bik}
                onChange={(e) => updateField("recipient_bik", e.target.value)}
              />
              {serverFieldErrors.recipient_bik ? (
                <p className="text-xs font-medium text-[var(--status-danger-text)] break-words">
                  {serverFieldErrors.recipient_bik}
                </p>
              ) : bikInvalidReasons.length > 0 ? (
                <p className="text-xs font-medium text-[var(--status-danger-text)] break-words">
                  {bikInvalidReasons.join(" ")}
                </p>
              ) : !bikMatchesDetectedBank && detectedBank ? (
                <div className="ui-notice ui-notice-warn flex flex-wrap items-center gap-2 px-2.5 py-1.5 text-xs">
                  <span className="min-w-0 flex-1 text-foreground break-words">
                    {interpolate(t.queue.bikMismatchWarning, {
                      expectedBik: detectedBank.bik,
                      bank: detectedBank.name,
                    })}
                  </span>
                  <Button
                    type="button"
                    variant="outline"
                    size="xs"
                    onClick={handleApplyDetectedBik}
                    className="shrink-0"
                  >
                    {interpolate(t.queue.applyExpectedBik, {
                      bik: detectedBank.bik,
                    })}
                  </Button>
                </div>
              ) : bikBankInfo ? (
                <p className="truncate text-xs text-muted-foreground">
                  {bikBankInfo.name}
                </p>
              ) : null}

              {bikDiffersFromHistory && matchedSupplier?.lastBik && (
                <div className="ui-notice ui-notice-warn px-2.5 py-1.5 text-xs text-foreground break-words">
                  {interpolate(t.queue.historyDiffBadge, {
                    old: matchedSupplier.lastBik,
                    current: cleanBik,
                  })}
                </div>
              )}
            </div>

            {/* IIK input: grouped by 4, uppercase, live mod-97, auto-bank & history diff */}
            <div className="min-w-0 space-y-1.5 sm:col-span-2">
              <Label htmlFor="dialog_recipient_iik">
                {t.queue.labelIik}
              </Label>
              <Input
                ref={iikInputRef}
                id="dialog_recipient_iik"
                aria-invalid={isIikInvalid}
                placeholder="KZ47 856K ZT50 0410 0100"
                className="h-10 bg-card font-mono uppercase tabular-nums sm:h-9"
                value={form.recipient_iik}
                onChange={(e) =>
                  updateField(
                    "recipient_iik",
                    e.target.value,
                    e.target.selectionStart
                  )
                }
              />

              {serverFieldErrors.recipient_iik ? (
                <p className="text-xs font-medium text-[var(--status-danger-text)] break-words">
                  {serverFieldErrors.recipient_iik}
                </p>
              ) : iikInvalidReasons.length > 0 ? (
                <p className="text-xs font-medium text-[var(--status-danger-text)] break-words">
                  {iikInvalidReasons.join(" ")}
                </p>
              ) : iikStatusMessage ? (
                <p
                  className={cn(
                    "text-xs break-words",
                    iikValidation.status === "valid"
                      ? "font-medium text-[var(--status-ok-text)]"
                      : iikValidation.status === "invalid"
                        ? "font-medium text-[var(--status-danger-text)]"
                        : "text-muted-foreground"
                  )}
                >
                  {iikStatusMessage}
                </p>
              ) : null}

              {detectedBank && (
                <p className="text-xs text-muted-foreground break-words">
                  {interpolate(t.queue.bankAutoDetected, {
                    bank: detectedBank.name,
                    bik: detectedBank.bik,
                  })}
                </p>
              )}

              {iikDiffersFromHistory && matchedSupplier?.lastIik && (
                <div className="ui-notice ui-notice-warn px-2.5 py-1.5 text-xs text-foreground break-all">
                  {interpolate(t.queue.historyDiffBadge, {
                    old: formatIikGrouped(matchedSupplier.lastIik),
                    current: formatIikGrouped(cleanIik),
                  })}
                </div>
              )}
            </div>

            {/* Amount input: thousands separators, ₸ suffix, decimal comma, typical amount hint */}
            <div className="min-w-0 space-y-1.5 sm:col-span-2">
              <div className="flex flex-wrap items-center justify-between gap-1.5">
                <Label htmlFor="dialog_amount_kzt">
                  {t.queue.labelAmount}
                </Label>
                {matchedSupplier?.typicalAmountKzt !== null &&
                  matchedSupplier?.typicalAmountKzt !== undefined && (
                    <span className="text-xs font-medium text-muted-foreground tabular-nums">
                      {interpolate(t.queue.supplierTypicalAmount, {
                        amount: formatMoney(matchedSupplier.typicalAmountKzt),
                      })}
                    </span>
                  )}
              </div>
              <div className="relative">
                <Input
                  ref={amountInputRef}
                  id="dialog_amount_kzt"
                  type="text"
                  inputMode="decimal"
                  aria-invalid={Boolean(serverFieldErrors.amount_kzt)}
                  placeholder="450 000"
                  className="h-10 bg-card pr-9 tabular-nums sm:h-9"
                  value={form.amount_kzt}
                  onChange={(e) =>
                    updateField(
                      "amount_kzt",
                      e.target.value,
                      e.target.selectionStart
                    )
                  }
                />
                <span
                  aria-hidden="true"
                  className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-sm font-medium text-muted-foreground"
                >
                  ₸
                </span>
              </div>
              {serverFieldErrors.amount_kzt && (
                <p className="text-xs font-medium text-[var(--status-danger-text)] break-words">
                  {serverFieldErrors.amount_kzt}
                </p>
              )}
            </div>

            <div className="min-w-0 space-y-1.5">
              <Label htmlFor="dialog_kbe">{t.queue.labelKbe}</Label>
              <Input
                ref={kbeInputRef}
                id="dialog_kbe"
                inputMode="numeric"
                maxLength={2}
                aria-invalid={Boolean(serverFieldErrors.kbe)}
                placeholder={t.queue.placeholderKbe}
                className="h-10 bg-card font-mono tabular-nums sm:h-9"
                value={form.kbe}
                onChange={(e) => updateField("kbe", e.target.value)}
              />
              {serverFieldErrors.kbe && (
                <p className="text-xs font-medium text-[var(--status-danger-text)] break-words">
                  {serverFieldErrors.kbe}
                </p>
              )}
            </div>

            <div className="min-w-0 space-y-1.5">
              <Label htmlFor="dialog_knp">{t.queue.labelKnp}</Label>
              <Input
                ref={knpInputRef}
                id="dialog_knp"
                inputMode="numeric"
                maxLength={3}
                aria-invalid={Boolean(serverFieldErrors.knp)}
                placeholder={t.queue.placeholderKnp}
                className="h-10 bg-card font-mono tabular-nums sm:h-9"
                value={form.knp}
                onChange={(e) => updateField("knp", e.target.value)}
              />
              {serverFieldErrors.knp && (
                <p className="text-xs font-medium text-[var(--status-danger-text)] break-words">
                  {serverFieldErrors.knp}
                </p>
              )}
            </div>

            <div className="min-w-0 space-y-1.5 sm:col-span-2">
              <Label htmlFor="dialog_purpose">{t.queue.labelPurpose}</Label>
              <Input
                ref={purposeInputRef}
                id="dialog_purpose"
                aria-invalid={Boolean(serverFieldErrors.purpose)}
                placeholder={t.queue.placeholderPurpose}
                className="h-10 bg-card sm:h-9"
                value={form.purpose}
                onChange={(e) => updateField("purpose", e.target.value)}
              />
              {serverFieldErrors.purpose && (
                <p className="text-xs font-medium text-[var(--status-danger-text)] break-words">
                  {serverFieldErrors.purpose}
                </p>
              )}
            </div>
          </div>

          {isConflictBlocked && (
            <p
              id={conflictHintId}
              role="status"
              className="ui-notice ui-notice-warn py-2 text-xs text-foreground break-words"
            >
              {t.queue.invoiceConflictBlockedHint}
            </p>
          )}

          {isConfirmationBlocked && (
            <p
              id={confirmHintId}
              role="status"
              className="ui-notice ui-notice-warn py-2 text-xs text-foreground break-words"
            >
              {t.invoice.submitBlockedHint}
            </p>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => handleClose(false)}
              disabled={isSubmitting}
              className="min-h-10 w-full sm:min-h-9 sm:w-auto"
            >
              {t.common.cancel}
            </Button>
            <Button
              type="submit"
              disabled={
                isSubmitting ||
                isExtractingInvoice ||
                isConfirmationBlocked ||
                isConflictBlocked
              }
              aria-describedby={
                isConflictBlocked
                  ? conflictHintId
                  : isConfirmationBlocked
                    ? confirmHintId
                    : undefined
              }
              className="min-h-10 w-full sm:min-h-9 sm:w-auto"
            >
              {isSubmitting ? (
                <>
                  <Loader2
                    className="size-4 animate-spin motion-reduce:animate-none"
                    aria-hidden="true"
                  />
                  <span>{t.queue.submitChecking}</span>
                </>
              ) : isEditMode ? (
                t.queue.submitFixCheck
              ) : (
                t.queue.submitCheck
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
