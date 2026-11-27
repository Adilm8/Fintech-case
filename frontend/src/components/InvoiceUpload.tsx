"use client";

import {
  useEffect,
  useId,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
} from "react";
import { Loader2, Mail, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import {
  getDictionary,
  interpolate as interpolateTemplate,
  useT,
  type Dictionary,
  type Lang,
} from "@/i18n";
import {
  INVOICE_ACCEPT_ATTRIBUTE,
  INVOICE_EXTRACT_TIMEOUT_MS,
  InvoiceExtractError,
  MAX_INVOICE_FILE_BYTES,
  extractInvoice,
  getInvoiceApiBase,
  getInvoiceErrorMessage,
  isInvoiceExtractAbortError,
  mapInvoiceToFormValues,
  needsManualConfirmation,
  parseInvoiceExtraction,
  validateInvoiceFile,
  type InvoiceExtraction,
} from "@/lib/invoice";
import { IS_PROD } from "@/lib/mode";
import { cn } from "cn";

const DEMO_SAMPLE_URL = "/samples/demo-invoice-alatau.txt";
const DEMO_SAMPLE_FILENAME = "demo-invoice-alatau.txt";

export interface InvoiceUploadProps {
  apiBase?: string | null;
  disabled?: boolean;
  showDemoSample?: boolean;
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

function normalizeApiBase(raw: string | null | undefined): string {
  if (typeof raw !== "string") return "";
  const trimmed = raw.trim().replace(/\/+$/, "");
  if (!trimmed) return "";
  if (
    trimmed.startsWith("http://") ||
    trimmed.startsWith("https://") ||
    trimmed.startsWith("/")
  ) {
    return trimmed;
  }
  return "";
}

function buildTextExtractHttpError(
  status: number,
  detail: unknown,
  dict: Dictionary
): InvoiceExtractError {
  const safeDetail =
    typeof detail === "string" && detail.trim() ? detail.trim() : null;

  if (status === 400) {
    return new InvoiceExtractError({
      code: "http_400",
      status,
      detail,
      message: safeDetail || dict.invoice.errors.http400,
    });
  }
  if (status === 413) {
    return new InvoiceExtractError({
      code: "http_413",
      status,
      detail,
      message: safeDetail || dict.invoice.errors.http413,
    });
  }
  if (status === 415) {
    return new InvoiceExtractError({
      code: "http_415",
      status,
      detail,
      message: safeDetail || dict.invoice.errors.http415,
    });
  }
  return new InvoiceExtractError({
    code: "http_other",
    status,
    detail,
    message:
      safeDetail ||
      interpolateTemplate(dict.invoice.errors.httpOther, { status }),
  });
}

/**
 * Posts a text/plain invoice sample to the same /api/invoice/extract endpoint used by
 * regular uploads so the backend runs deterministic local template extraction.
 */
async function extractTextPlainInvoice(
  file: File,
  options: { apiBase?: string | null; signal?: AbortSignal; lang: Lang }
): Promise<InvoiceExtraction> {
  const dict = getDictionary(options.lang);

  if (file.size <= 0) {
    throw new InvoiceExtractError({
      code: "empty_file",
      status: 0,
      message: dict.invoice.errors.emptyFile,
    });
  }
  if (file.size > MAX_INVOICE_FILE_BYTES) {
    throw new InvoiceExtractError({
      code: "too_large",
      status: 0,
      message: dict.invoice.errors.tooLarge,
    });
  }

  const hasExplicitApiBase =
    options.apiBase !== undefined && options.apiBase !== null;
  const resolvedApiBase = hasExplicitApiBase
    ? normalizeApiBase(options.apiBase)
    : getInvoiceApiBase();

  if (!IS_PROD && !resolvedApiBase) {
    throw new InvoiceExtractError({
      code: "missing_api_base",
      status: 0,
      message: dict.invoice.errors.apiBaseMissing,
    });
  }

  const externalSignal = options.signal;
  if (externalSignal?.aborted) {
    throw new DOMException("The operation was aborted.", "AbortError");
  }

  const controller = new AbortController();
  let timedOut = false;
  const onExternalAbort = () => controller.abort();
  externalSignal?.addEventListener("abort", onExternalAbort, { once: true });

  const timeoutId = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, INVOICE_EXTRACT_TIMEOUT_MS);

  const filename = file.name?.trim() || DEMO_SAMPLE_FILENAME;
  const url = `${resolvedApiBase}/api/invoice/extract?filename=${encodeURIComponent(filename)}`;
  const headers: Record<string, string> = {
    "Content-Type": "text/plain",
  };
  if (IS_PROD) {
    headers["X-Shield-Request"] = "1";
  }

  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers,
      body: file,
      credentials: IS_PROD ? "include" : "omit",
      cache: "no-store",
      signal: controller.signal,
    });
  } catch (err) {
    if (timedOut) {
      throw new InvoiceExtractError({
        code: "timeout",
        status: 0,
        message: dict.invoice.errors.timeout,
      });
    }
    if (externalSignal?.aborted || isInvoiceExtractAbortError(err)) {
      throw err;
    }
    throw new InvoiceExtractError({
      code: "network",
      status: 0,
      message: dict.invoice.errors.network,
    });
  } finally {
    clearTimeout(timeoutId);
    externalSignal?.removeEventListener("abort", onExternalAbort);
  }

  let body: unknown = null;
  const responseContentType = response.headers.get("content-type") || "";
  if (responseContentType.includes("application/json")) {
    try {
      body = await response.json();
    } catch {
      body = null;
    }
  } else {
    try {
      const text = await response.text();
      if (text) {
        try {
          body = JSON.parse(text);
        } catch {
          body = text;
        }
      }
    } catch {
      body = null;
    }
  }

  if (!response.ok) {
    const detail =
      body && typeof body === "object" && "detail" in body
        ? (body as { detail: unknown }).detail
        : body;
    throw buildTextExtractHttpError(response.status, detail, dict);
  }

  return parseInvoiceExtraction(body, options.lang);
}

export function InvoiceUpload({
  apiBase,
  disabled = false,
  showDemoSample = !IS_PROD,
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
  const [loadingSource, setLoadingSource] = useState<"file" | "demo">("file");
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
    setLoadingSource("file");
    setStatus("idle");
    setSelectedFile(null);
    setErrorMessage(null);
    setResult(null);
    resetFileInput();
    updateConfirmed(false);
    onLoadingChange?.(false);
    onClear?.();
  };

  const handleFile = async (
    file: File,
    options?: {
      allowTextPlain?: boolean;
      existingRequestId?: number;
      existingController?: AbortController;
    }
  ) => {
    if (disabled) return;

    const isContinuingDemo =
      options?.existingRequestId !== undefined &&
      options?.existingController !== undefined;
    const isTextPlainSample =
      Boolean(options?.allowTextPlain) &&
      (file.type || "").trim().toLowerCase() === "text/plain";

    let currentRequestId: number;
    let controller: AbortController;

    if (isContinuingDemo) {
      currentRequestId = options.existingRequestId!;
      controller = options.existingController!;
      if (requestIdRef.current !== currentRequestId) {
        return;
      }
    } else {
      abortControllerRef.current?.abort();
      abortControllerRef.current = null;
      currentRequestId = ++requestIdRef.current;
      resetFileInput();
      setLoadingSource("file");

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
      setErrorMessage(null);
      setResult(null);
      setStatus("loading");
      onLoadingChange?.(true);

      controller = new AbortController();
      abortControllerRef.current = controller;
    }

    setSelectedFile({ name: file.name, size: file.size });

    try {
      const extracted = isTextPlainSample
        ? await extractTextPlainInvoice(file, {
            apiBase,
            signal: controller.signal,
            lang,
          })
        : await extractInvoice(file, {
            apiBase,
            signal: controller.signal,
            lang,
          });

      if (requestIdRef.current !== currentRequestId) {
        return;
      }

      abortControllerRef.current = null;
      setLoadingSource("file");
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
      setLoadingSource("file");
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

  const handleLoadDemoSample = async () => {
    if (isDisabled) return;

    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    const currentRequestId = ++requestIdRef.current;
    resetFileInput();

    onClear?.();
    updateConfirmed(false);
    setLoadingSource("demo");
    setSelectedFile({ name: DEMO_SAMPLE_FILENAME, size: 0 });
    setErrorMessage(null);
    setResult(null);
    setStatus("loading");
    onLoadingChange?.(true);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    let sampleFile: File;
    try {
      const response = await fetch(DEMO_SAMPLE_URL, {
        cache: "no-store",
        signal: controller.signal,
      });
      if (!response.ok) {
        throw new Error(t.invoice.errors.demoSampleLoadFailed);
      }
      const blob = await response.blob();
      if (requestIdRef.current !== currentRequestId) {
        return;
      }
      sampleFile = new File([blob], DEMO_SAMPLE_FILENAME, {
        type: "text/plain",
      });
    } catch (err) {
      if (requestIdRef.current !== currentRequestId) {
        return;
      }

      abortControllerRef.current = null;
      setLoadingSource("file");
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
      setSelectedFile(null);
      setErrorMessage(t.invoice.errors.demoSampleLoadFailed);
      setStatus("error");
      updateConfirmed(false);
      return;
    }

    await handleFile(sampleFile, {
      allowTextPlain: true,
      existingRequestId: currentRequestId,
      existingController: controller,
    });
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
          "min-w-0 transition-colors motion-reduce:transition-none",
          status === "success"
            ? "ui-panel p-3"
            : "ui-dropzone",
          isDragOver && "border-primary bg-muted/60",
          status === "error" && !isDragOver && "border-destructive"
        )}
      >
        {status === "loading" ? (
          <div
            role="status"
            aria-live="polite"
            className="flex w-full min-w-0 flex-col gap-2.5 sm:flex-row sm:items-center sm:justify-between"
          >
            <div className="flex min-w-0 items-start gap-2">
              <Loader2
                aria-hidden="true"
                className="mt-0.5 size-4 shrink-0 animate-spin text-muted-foreground motion-reduce:animate-none"
              />
              <div className="min-w-0 flex-1 space-y-0.5">
                <div className="text-sm font-medium text-foreground break-words">
                  {loadingSource === "demo"
                    ? t.invoice.demoSampleLoading
                    : t.invoice.loadingTitle}
                </div>
                {selectedFile && (
                  <div className="text-xs text-muted-foreground tabular-nums break-all">
                    {selectedFile.size > 0
                      ? `${selectedFile.name} · ${formatFileSize(selectedFile.size)}`
                      : selectedFile.name}
                  </div>
                )}
              </div>
            </div>

            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={resetToIdle}
              className="min-h-10 w-full shrink-0 sm:min-h-8 sm:w-auto"
            >
              {t.invoice.cancelUploadButton}
            </Button>
          </div>
        ) : status === "success" && result ? (
          <div className="w-full min-w-0 space-y-2.5">
            <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
              <div className="flex min-w-0 items-center gap-2">
                <span className="ui-status">
                  <span
                    aria-hidden="true"
                    className={cn(
                      "ui-status-dot",
                      requiresConfirmation ? "ui-dot-warn" : "ui-dot-ok"
                    )}
                  />
                  <span>{t.invoice.label}</span>
                </span>
                {selectedFile && (
                  <span className="min-w-0 truncate text-xs text-muted-foreground tabular-nums">
                    {selectedFile.name} · {formatFileSize(selectedFile.size)}
                  </span>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-1.5">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={openFilePicker}
                  disabled={disabled}
                  className="min-h-10 sm:min-h-8"
                >
                  {t.invoice.replaceButton}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  onClick={resetToIdle}
                  disabled={disabled}
                  aria-label={t.invoice.aria.removeFile}
                  className="size-10 text-muted-foreground hover:text-foreground sm:size-8"
                >
                  <X className="size-4" />
                </Button>
              </div>
            </div>

            <p
              role="status"
              aria-live="polite"
              className="text-xs text-muted-foreground tabular-nums break-words"
            >
              {t.invoice.sourceLabel}: {t.invoice.sources[result.source]}
              {" · "}
              {interpolate(t.invoice.confidenceLabel, {
                percent: confidencePercent,
              })}
            </p>

            {extractedValuesCount === 0 && result.warnings.length === 0 && (
              <p className="text-xs leading-relaxed text-muted-foreground break-words">
                {t.invoice.noFieldsExtracted}
              </p>
            )}

            {result.warnings.length > 0 && (
              <div className="ui-notice ui-notice-warn min-w-0 space-y-1">
                <div className="text-xs font-medium text-[var(--status-warn-text)]">
                  {interpolate(t.invoice.warningsTitle, {
                    count: result.warnings.length,
                  })}
                </div>
                <ul className="min-w-0 list-disc space-y-0.5 pl-4 text-xs leading-5 text-foreground">
                  {result.warnings.map((warning, idx) => (
                    <li key={`${idx}-${warning}`} className="break-words">
                      {warning}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {requiresConfirmation && (
              <div
                className={cn(
                  "flex min-h-10 min-w-0 items-start gap-2.5",
                  isConfirmed ? "ui-subpanel" : "ui-notice ui-notice-warn"
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
                <div className="min-w-0 flex-1 space-y-0.5">
                  <Label
                    htmlFor={checkboxId}
                    className="cursor-pointer text-xs font-medium leading-snug text-foreground break-words"
                  >
                    {t.invoice.confirmCheckboxLabel}
                  </Label>
                  {!isConfirmed && (
                    <p className="text-xs leading-snug text-[var(--status-warn-text)] break-words">
                      {t.invoice.confirmRequiredHint}
                    </p>
                  )}
                </div>
              </div>
            )}

            {isDragOver && (
              <p className="text-xs font-medium text-[var(--brand-text)]">
                {t.invoice.dropActiveHint}
              </p>
            )}
          </div>
        ) : (
          <div className="w-full min-w-0 space-y-2.5">
            {status === "error" && errorMessage && (
              <div
                role="alert"
                aria-live="assertive"
                className="ui-notice ui-notice-danger flex items-start justify-between gap-2 py-2"
              >
                <p className="min-w-0 text-xs leading-5 text-foreground break-words">
                  {errorMessage}
                </p>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-xs"
                  onClick={resetToIdle}
                  disabled={disabled}
                  aria-label={t.invoice.aria.removeFile}
                  className="shrink-0 text-muted-foreground hover:text-foreground"
                >
                  <X className="size-3.5" />
                </Button>
              </div>
            )}

            <div className="flex min-w-0 flex-col gap-2.5">
              <div className="flex min-w-0 flex-col gap-2.5 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0 space-y-0.5">
                  <div className="text-[13px] font-medium text-foreground break-words">
                    {isDragOver ? t.invoice.dropActiveHint : t.invoice.label}
                  </div>
                  <p className="text-xs text-muted-foreground break-words">
                    {t.invoice.dropHint} · {t.invoice.formatsHint}
                  </p>
                </div>

                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={openFilePicker}
                  disabled={isDisabled}
                  className="min-h-10 w-full shrink-0 sm:min-h-8 sm:w-auto"
                >
                  {t.invoice.uploadButton}
                </Button>
              </div>

              {showDemoSample && (
                <div className="flex flex-wrap items-center gap-2 border-t border-border/70 pt-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => void handleLoadDemoSample()}
                    disabled={isDisabled}
                    aria-label={t.invoice.aria.demoSampleButton}
                    className="min-h-10 w-full border-[#00AB75]/45 bg-[var(--brand-subtle)] text-[var(--brand-text)] hover:border-[#00AB75] hover:bg-[#00AB75]/10 hover:text-[var(--brand-text)] sm:min-h-8 sm:w-auto"
                  >
                    <Mail
                      aria-hidden="true"
                      className="size-3.5 text-[#00AB75]"
                    />
                    <span>{t.invoice.demoSampleButton}</span>
                  </Button>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      <p
        id={privacyNoteId}
        className="text-xs leading-4 text-muted-foreground break-words"
      >
        {t.invoice.privacyNotice}
      </p>
    </section>
  );
}
