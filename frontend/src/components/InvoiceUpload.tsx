"use client";

import {
  useEffect,
  useId,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
} from "react";
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  FileText,
  Loader2,
  RefreshCw,
  Upload,
  X,
} from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { useT } from "@/i18n";
import {
  INVOICE_ACCEPT_ATTRIBUTE,
  extractInvoice,
  getInvoiceErrorMessage,
  isInvoiceExtractAbortError,
  mapInvoiceToFormValues,
  needsManualConfirmation,
  validateInvoiceFile,
  type InvoiceExtraction,
  type InvoiceExtractionSource,
} from "@/lib/invoice";
import { cn } from "cn";

export interface InvoiceUploadProps {
  apiBase?: string | null;
  disabled?: boolean;
  confirmed?: boolean;
  onExtracted: (result: InvoiceExtraction) => void;
  onConfirmedChange?: (confirmed: boolean) => void;
  onClear?: () => void;
  onLoadingChange?: (loading: boolean) => void;
  className?: string;
}

type UploadStatus = "idle" | "loading" | "error" | "success";

interface SelectedFileMeta {
  name: string;
  size: number;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function getSourceBadgeClass(source: InvoiceExtractionSource): string {
  if (source === "claude") {
    return "border-[#00AB75]/30 bg-[#00AB75]/10 text-[#006B49] dark:border-emerald-700/60 dark:bg-emerald-950/40 dark:text-emerald-200";
  }
  if (source === "text_rules") {
    return "border-border bg-secondary text-secondary-foreground";
  }
  return "border-amber-300/80 bg-amber-50 text-amber-900 dark:border-amber-700/60 dark:bg-amber-950/40 dark:text-amber-200";
}

function getConfidenceBadgeClass(confidence: number): string {
  if (confidence >= 0.8) {
    return "border-[#00AB75]/30 bg-[#00AB75]/10 text-[#006B49] dark:border-emerald-700/60 dark:bg-emerald-950/40 dark:text-emerald-200";
  }
  if (confidence >= 0.5) {
    return "border-border bg-muted text-foreground";
  }
  return "border-amber-300/80 bg-amber-50 text-amber-900 dark:border-amber-700/60 dark:bg-amber-950/40 dark:text-amber-200";
}

export function InvoiceUpload({
  apiBase,
  disabled = false,
  confirmed,
  onExtracted,
  onConfirmedChange,
  onClear,
  onLoadingChange,
  className,
}: InvoiceUploadProps) {
  const { t, lang, interpolate } = useT();

  const fileInputId = useId();
  const checkboxId = useId();
  const privacyNoteId = useId();

  const fileInputRef = useRef<HTMLInputElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const requestIdRef = useRef(0);
  const dragDepthRef = useRef(0);

  const [status, setStatus] = useState<UploadStatus>("idle");
  const [isDragOver, setIsDragOver] = useState(false);
  const [selectedFile, setSelectedFile] = useState<SelectedFileMeta | null>(
    null
  );
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [result, setResult] = useState<InvoiceExtraction | null>(null);
  const [uncontrolledConfirmed, setUncontrolledConfirmed] = useState(false);

  const isConfirmed =
    confirmed !== undefined ? confirmed : uncontrolledConfirmed;
  const isLoading = status === "loading";
  const isDisabled = disabled || isLoading;

  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
      abortControllerRef.current = null;
    };
  }, []);

  const updateConfirmed = (next: boolean) => {
    if (confirmed === undefined) {
      setUncontrolledConfirmed(next);
    }
    onConfirmedChange?.(next);
  };

  const resetFileInput = () => {
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const resetToIdle = () => {
    requestIdRef.current += 1;
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    dragDepthRef.current = 0;
    setIsDragOver(false);
    setStatus("idle");
    setSelectedFile(null);
    setErrorMessage(null);
    setResult(null);
    resetFileInput();
    updateConfirmed(false);
    onLoadingChange?.(false);
    onClear?.();
  };

  const handleFile = async (file: File) => {
    if (disabled) return;

    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    const currentRequestId = ++requestIdRef.current;
    resetFileInput();

    const validation = validateInvoiceFile(file, lang);
    if (!validation.ok) {
      setSelectedFile({ name: file.name, size: file.size });
      setResult(null);
      setErrorMessage(validation.message);
      setStatus("error");
      updateConfirmed(false);
      onLoadingChange?.(false);
      onClear?.();
      return;
    }

    onClear?.();
    updateConfirmed(false);
    setSelectedFile({ name: file.name, size: file.size });
    setErrorMessage(null);
    setResult(null);
    setStatus("loading");
    onLoadingChange?.(true);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const extracted = await extractInvoice(file, {
        apiBase,
        signal: controller.signal,
        lang,
      });

      if (requestIdRef.current !== currentRequestId) {
        return;
      }

      abortControllerRef.current = null;
      setResult(extracted);
      setErrorMessage(null);
      setStatus("success");
      updateConfirmed(false);
      onLoadingChange?.(false);
      onExtracted(extracted);
    } catch (err) {
      if (requestIdRef.current !== currentRequestId) {
        return;
      }

      abortControllerRef.current = null;
      onLoadingChange?.(false);

      if (isInvoiceExtractAbortError(err)) {
        setStatus("idle");
        setSelectedFile(null);
        setErrorMessage(null);
        setResult(null);
        updateConfirmed(false);
        return;
      }

      setResult(null);
      setErrorMessage(getInvoiceErrorMessage(err, lang));
      setStatus("error");
      updateConfirmed(false);
    }
  };

  const handleInputChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      void handleFile(file);
    }
  };

  const openFilePicker = () => {
    if (isDisabled) return;
    fileInputRef.current?.click();
  };

  const handleDragEnter = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (isDisabled) return;
    dragDepthRef.current += 1;
    setIsDragOver(true);
  };

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (isDisabled) return;
    e.dataTransfer.dropEffect = "copy";
    if (!isDragOver) {
      setIsDragOver(true);
    }
  };

  const handleDragLeave = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
    if (dragDepthRef.current === 0) {
      setIsDragOver(false);
    }
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    dragDepthRef.current = 0;
    setIsDragOver(false);
    if (isDisabled) return;
    const file = e.dataTransfer.files?.[0];
    if (file) {
      void handleFile(file);
    }
  };

  const requiresConfirmation =
    result !== null && needsManualConfirmation(result);
  const confidencePercent =
    result !== null ? Math.round(result.confidence * 100) : 0;
  const extractedValuesCount =
    result !== null ? Object.keys(mapInvoiceToFormValues(result)).length : 0;

  return (
    <section
      aria-label={t.invoice.label}
      className={cn("min-w-0 space-y-2", className)}
    >
      <input
        id={fileInputId}
        ref={fileInputRef}
        type="file"
        accept={INVOICE_ACCEPT_ATTRIBUTE}
        onChange={handleInputChange}
        disabled={isDisabled}
        aria-label={t.invoice.aria.fileInput}
        className="sr-only"
      />

      <div
        role="region"
        aria-label={t.invoice.aria.dropzone}
        aria-describedby={privacyNoteId}
        aria-busy={isLoading}
        onDragEnter={handleDragEnter}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={cn(
          "min-w-0 rounded-xl border transition-colors motion-reduce:transition-none",
          status === "success"
            ? "border-border bg-card p-3 sm:p-3.5"
            : "border-dashed bg-background/60 p-3 sm:p-3.5",
          isDragOver &&
            "border-primary bg-accent/50 ring-2 ring-primary/25 dark:bg-accent/20",
          status === "error" &&
            !isDragOver &&
            "border-red-300/90 dark:border-red-800/70",
          !isDragOver && status !== "error" && "border-border"
        )}
      >
        {status === "loading" ? (
          <div
            role="status"
            aria-live="polite"
            className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"
          >
            <div className="flex min-w-0 items-start gap-2.5">
              <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-accent text-[var(--brand-text)]">
                <Loader2
                  aria-hidden="true"
                  className="size-4 animate-spin motion-reduce:animate-none"
                />
              </div>
              <div className="min-w-0 flex-1 space-y-0.5">
                <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  {t.invoice.label}
                </div>
                <div className="text-sm font-medium text-foreground break-words">
                  {t.invoice.loadingTitle}
                </div>
                {selectedFile && (
                  <div className="text-xs text-muted-foreground break-all">
                    {selectedFile.name} · {formatFileSize(selectedFile.size)}
                  </div>
                )}
              </div>
            </div>

            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={resetToIdle}
              className="min-h-11 w-full shrink-0 gap-1.5 sm:min-h-9 sm:w-auto"
            >
              <X className="size-3.5" />
              <span>{t.invoice.cancelUploadButton}</span>
            </Button>
          </div>
        ) : status === "success" && result ? (
          <div className="min-w-0 space-y-3">
            <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
              <div className="flex min-w-0 items-center gap-2">
                <div
                  className={cn(
                    "flex size-7 shrink-0 items-center justify-center rounded-lg",
                    requiresConfirmation
                      ? "bg-amber-100/90 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300"
                      : "bg-accent text-[var(--brand-text)]"
                  )}
                >
                  {requiresConfirmation ? (
                    <AlertTriangle aria-hidden="true" className="size-4" />
                  ) : (
                    <CheckCircle2 aria-hidden="true" className="size-4" />
                  )}
                </div>
                <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground break-words">
                  {t.invoice.label}
                </span>
              </div>

              <div className="flex flex-wrap items-center gap-1.5">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={openFilePicker}
                  disabled={disabled}
                  className="min-h-11 gap-1.5 px-2.5 text-xs sm:min-h-8"
                >
                  <RefreshCw className="size-3.5" />
                  <span>{t.invoice.replaceButton}</span>
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  onClick={resetToIdle}
                  disabled={disabled}
                  aria-label={t.invoice.aria.removeFile}
                  className="size-11 text-muted-foreground hover:text-foreground sm:size-8"
                >
                  <X className="size-4" />
                </Button>
              </div>
            </div>

            {selectedFile && (
              <div className="flex min-w-0 items-center gap-1.5 text-xs text-muted-foreground">
                <FileText aria-hidden="true" className="size-3.5 shrink-0" />
                <span className="min-w-0 truncate font-medium text-foreground">
                  {selectedFile.name}
                </span>
                <span className="shrink-0">
                  · {formatFileSize(selectedFile.size)}
                </span>
              </div>
            )}

            <div
              role="status"
              aria-live="polite"
              className="flex min-w-0 flex-wrap items-center gap-1.5"
            >
              <Badge
                variant="outline"
                className={cn(
                  "h-auto max-w-full whitespace-normal px-2.5 py-0.5 text-xs font-medium",
                  getSourceBadgeClass(result.source)
                )}
              >
                {t.invoice.sourceLabel}: {t.invoice.sources[result.source]}
              </Badge>

              <Badge
                variant="outline"
                className={cn(
                  "h-auto max-w-full whitespace-normal px-2.5 py-0.5 text-xs font-medium tabular-nums",
                  getConfidenceBadgeClass(result.confidence)
                )}
              >
                {interpolate(t.invoice.confidenceLabel, {
                  percent: confidencePercent,
                })}
              </Badge>
            </div>

            {extractedValuesCount === 0 && result.warnings.length === 0 && (
              <p className="text-xs leading-relaxed text-muted-foreground break-words">
                {t.invoice.noFieldsExtracted}
              </p>
            )}

            {result.warnings.length > 0 && (
              <div className="min-w-0 space-y-1.5">
                <div className="text-xs font-semibold text-amber-900 dark:text-amber-200">
                  {interpolate(t.invoice.warningsTitle, {
                    count: result.warnings.length,
                  })}
                </div>
                <ul className="min-w-0 space-y-1.5">
                  {result.warnings.map((warning, idx) => (
                    <li
                      key={`${idx}-${warning}`}
                      className="flex min-w-0 items-start gap-2 rounded-lg border border-amber-300/90 bg-amber-50/90 px-2.5 py-2 text-xs leading-snug text-amber-950 dark:border-amber-700/60 dark:bg-amber-950/40 dark:text-amber-100"
                    >
                      <AlertTriangle
                        aria-hidden="true"
                        className="mt-0.5 size-3.5 shrink-0 text-amber-700 dark:text-amber-400"
                      />
                      <span className="min-w-0 flex-1 break-words">
                        {warning}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {requiresConfirmation && (
              <div
                className={cn(
                  "flex min-h-11 min-w-0 items-start gap-2.5 rounded-xl border px-3 py-2.5 transition-colors motion-reduce:transition-none",
                  isConfirmed
                    ? "border-[#00AB75]/35 bg-[#E8F8F2]/60 dark:border-emerald-700/60 dark:bg-emerald-950/30"
                    : "border-amber-300/90 bg-amber-50/75 dark:border-amber-700/60 dark:bg-amber-950/35"
                )}
              >
                <Checkbox
                  id={checkboxId}
                  checked={isConfirmed}
                  onCheckedChange={(checked) =>
                    updateConfirmed(Boolean(checked))
                  }
                  disabled={disabled}
                  className="mt-0.5"
                />
                <div className="min-w-0 flex-1 space-y-1">
                  <Label
                    htmlFor={checkboxId}
                    className="cursor-pointer text-xs font-medium leading-snug text-foreground break-words"
                  >
                    {t.invoice.confirmCheckboxLabel}
                  </Label>
                  {!isConfirmed && (
                    <p className="text-[11px] leading-snug text-amber-900 dark:text-amber-200 break-words">
                      {t.invoice.confirmRequiredHint}
                    </p>
                  )}
                </div>
              </div>
            )}

            {isDragOver && (
              <p className="text-center text-xs font-medium text-[var(--brand-text)]">
                {t.invoice.dropActiveHint}
              </p>
            )}
          </div>
        ) : (
          <div className="min-w-0 space-y-2.5">
            <div className="flex min-w-0 items-center justify-between gap-2">
              <div className="flex min-w-0 items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                <FileText
                  aria-hidden="true"
                  className="size-3.5 shrink-0 text-[var(--brand-text)]"
                />
                <span className="truncate">{t.invoice.label}</span>
              </div>
              {status === "error" && (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  onClick={resetToIdle}
                  disabled={disabled}
                  aria-label={t.invoice.aria.removeFile}
                  className="size-11 shrink-0 text-muted-foreground hover:text-foreground sm:size-7"
                >
                  <X className="size-3.5" />
                </Button>
              )}
            </div>

            {status === "error" && errorMessage && (
              <Alert
                variant="destructive"
                aria-live="assertive"
                className="border-red-300 bg-red-50/90 dark:border-red-800/70 dark:bg-red-950/40"
              >
                <AlertCircle className="size-4" />
                <AlertDescription className="min-w-0 break-words">
                  {errorMessage}
                </AlertDescription>
              </Alert>
            )}

            <div className="flex min-w-0 flex-col items-center gap-2 py-1 text-center">
              <Button
                type="button"
                variant="outline"
                onClick={openFilePicker}
                disabled={isDisabled}
                className="min-h-11 h-auto w-full gap-2 whitespace-normal rounded-xl border-primary/35 bg-card px-3.5 py-2.5 text-center font-medium text-foreground shadow-xs hover:border-primary/60 hover:bg-accent/50 sm:min-h-10 sm:w-auto"
              >
                <Upload
                  aria-hidden="true"
                  className="size-4 shrink-0 text-[var(--brand-text)]"
                />
                <span>{t.invoice.uploadButton}</span>
              </Button>

              <div className="min-w-0 space-y-0.5 text-xs text-muted-foreground">
                <p className="break-words">
                  {isDragOver ? t.invoice.dropActiveHint : t.invoice.dropHint}
                </p>
                <p className="text-[11px] break-words">
                  {t.invoice.formatsHint}
                </p>
              </div>
            </div>
          </div>
        )}
      </div>

      <p
        id={privacyNoteId}
        className="text-[11px] leading-relaxed text-muted-foreground break-words"
      >
        {t.invoice.privacyNotice}
      </p>
    </section>
  );
}
