"use client";

import { useRef, useState, type ChangeEvent } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, Loader2 } from "lucide-react";
import { VerdictBadge } from "@/components/VerdictBadge";
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
import { Label } from "@/components/ui/label";
import { useT } from "@/i18n";
import {
  ApiError,
  getProdErrorMessage,
  importPayments,
} from "@/lib/prod/api";
import {
  MAX_IMPORT_FILE_BYTES,
  type ImportFormat,
  type ImportResult,
  type Verdict,
} from "@/lib/prod/types";
import { notify } from "@/lib/toast";
import { cn } from "cn";

interface ImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onImported: (result: ImportResult) => void;
}

const VERDICT_ORDER: readonly Verdict[] = [
  "green",
  "yellow",
  "red",
  "grey",
  "invalid",
] as const;

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function ImportDialog({
  open,
  onOpenChange,
  onImported,
}: ImportDialogProps) {
  const router = useRouter();
  const { t, lang, interpolate } = useT();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [format, setFormat] = useState<ImportFormat>("auto");
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [duplicatePrompt, setDuplicatePrompt] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);

  const resetState = () => {
    setSelectedFile(null);
    setFormat("auto");
    setError(null);
    setDuplicatePrompt(false);
    setResult(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen && isUploading) return;
    if (!nextOpen) {
      resetState();
    }
    onOpenChange(nextOpen);
  };

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] ?? null;
    setSelectedFile(file);
    setError(null);
    setDuplicatePrompt(false);
    setResult(null);
    if (file && file.size > MAX_IMPORT_FILE_BYTES) {
      setError(t.prod.import.fileTooLargeLocal);
    }
  };

  const runUpload = async (force: boolean) => {
    if (!selectedFile || isUploading) return;
    if (selectedFile.size > MAX_IMPORT_FILE_BYTES) {
      setError(t.prod.import.fileTooLargeLocal);
      return;
    }

    setError(null);
    setIsUploading(true);
    try {
      const importResult = await importPayments(
        selectedFile,
        {
          filename: selectedFile.name,
          format,
          force,
        },
        lang
      );
      setDuplicatePrompt(false);
      setResult(importResult);
      onImported(importResult);
      notify.success(
        t.prod.import.resultTitle,
        `${importResult.batch.filename}: ${importResult.summary.created}/${importResult.summary.total}`
      );
    } catch (err) {
      if (err instanceof ApiError && err.code === "duplicate_file") {
        setDuplicatePrompt(true);
        setError(null);
      } else {
        setDuplicatePrompt(false);
        setError(getProdErrorMessage(err));
      }
    } finally {
      setIsUploading(false);
    }
  };

  const handleOpenBatch = () => {
    if (!result) return;
    const batchId = result.batch.id;
    onOpenChange(false);
    resetState();
    router.push(`/payments?batch_id=${encodeURIComponent(batchId)}`);
  };

  const formatOptions: Array<{ value: ImportFormat; label: string }> = [
    { value: "auto", label: t.prod.import.formatAuto },
    { value: "1c", label: t.prod.import.format1c },
    { value: "csv", label: t.prod.import.formatCsv },
  ];

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent mobileSheet className="sm:max-w-xl">
        <div
          aria-hidden="true"
          className="mx-auto -mt-1 mb-1 h-1.5 w-10 rounded-full bg-border sm:hidden"
        />

        <DialogHeader>
          <DialogTitle>{t.prod.import.title}</DialogTitle>
          <DialogDescription>{t.prod.import.description}</DialogDescription>
        </DialogHeader>

        {result ? (
          <div className="space-y-4">
            <div role="status" className="ui-notice ui-notice-ok text-sm font-medium">
              <span className="break-all">
                {result.batch.filename} ({result.batch.source.toUpperCase()})
              </span>
            </div>

            <div className="ui-kpi-strip">
              <div className="ui-kpi-cell">
                <span className="ui-kpi-label">{t.prod.import.statTotal}</span>
                <span className="ui-kpi-value">{result.summary.total}</span>
              </div>
              <div className="ui-kpi-cell">
                <span className="ui-kpi-label">{t.prod.import.statCreated}</span>
                <span className="ui-kpi-value text-[var(--status-ok-text)]">
                  {result.summary.created}
                </span>
              </div>
              <div className="ui-kpi-cell">
                <span className="ui-kpi-label">{t.prod.import.statFailed}</span>
                <span
                  className={cn(
                    "ui-kpi-value",
                    result.summary.failed > 0 &&
                      "text-[var(--status-danger-text)]"
                  )}
                >
                  {result.summary.failed}
                </span>
              </div>
              <div className="ui-kpi-cell">
                <span className="ui-kpi-label">
                  {t.prod.import.statDuplicates}
                </span>
                <span
                  className={cn(
                    "ui-kpi-value",
                    result.summary.duplicates > 0 &&
                      "text-[var(--status-warn-text)]"
                  )}
                >
                  {result.summary.duplicates}
                </span>
              </div>
            </div>

            <div className="space-y-2">
              <div className="ui-label-meta">
                {t.prod.import.verdictBreakdown}
              </div>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
                {VERDICT_ORDER.map((v) => {
                  const count = result.summary.by_verdict[v] ?? 0;
                  if (count === 0) return null;
                  return (
                    <VerdictBadge
                      key={v}
                      verdict={v}
                      label={`${t.verdicts[v]}: ${count}`}
                      className="tabular-nums"
                    />
                  );
                })}
              </div>
            </div>

            {result.errors.length > 0 && (
              <div className="space-y-2">
                <div className="ui-label-meta text-[var(--status-danger-text)]">
                  {interpolate(t.prod.import.errorsTitle, {
                    count: result.errors.length,
                  })}
                </div>
                <div className="max-h-48 divide-y divide-border overflow-y-auto rounded-[6px] border border-border bg-card">
                  {result.errors.map((errItem, idx) => (
                    <div
                      key={`${errItem.code}-${errItem.line_no ?? "x"}-${idx}`}
                      className="px-3 py-2 text-xs space-y-1"
                    >
                      <div className="flex flex-wrap items-center gap-1.5 font-medium text-foreground">
                        {errItem.line_no !== null && (
                          <span className="ui-tag font-mono">
                            {interpolate(t.prod.import.linePrefix, {
                              line: errItem.line_no,
                            })}
                          </span>
                        )}
                        {errItem.doc_number && (
                          <span className="ui-tag">
                            {interpolate(t.prod.import.docPrefix, {
                              doc: errItem.doc_number,
                            })}
                          </span>
                        )}
                        <span className="font-mono text-[11px] text-muted-foreground">
                          {errItem.code}
                        </span>
                      </div>
                      <p className="text-muted-foreground break-words">
                        {errItem.message}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={resetState}
                className="min-h-11 w-full sm:min-h-9 sm:w-auto"
              >
                {t.prod.import.importAnother}
              </Button>
              <Button
                type="button"
                onClick={handleOpenBatch}
                className="min-h-11 w-full sm:min-h-9 sm:w-auto"
              >
                {t.prod.import.openBatchButton}
              </Button>
            </DialogFooter>
          </div>
        ) : (
          <div className="space-y-4">
            {error && (
              <Alert variant="destructive">
                <AlertCircle className="size-4" />
                <AlertDescription className="break-words">
                  {error}
                </AlertDescription>
              </Alert>
            )}

            {duplicatePrompt && (
              <div
                role="alert"
                className="ui-notice ui-notice-warn space-y-2.5 text-sm"
              >
                <div className="font-medium text-foreground">
                  {t.prod.import.duplicateTitle}
                </div>
                <p className="text-xs leading-relaxed text-muted-foreground">
                  {t.prod.import.duplicateDescription}
                </p>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => void runUpload(true)}
                  disabled={isUploading}
                  className="min-h-10 sm:min-h-8"
                >
                  {isUploading ? (
                    <>
                      <Loader2 className="size-3.5 animate-spin" />
                      <span>{t.prod.import.reloading}</span>
                    </>
                  ) : (
                    <span>{t.prod.import.forceReload}</span>
                  )}
                </Button>
              </div>
            )}

            <div className="space-y-1.5">
              <input
                ref={fileInputRef}
                type="file"
                accept=".txt,.csv,text/plain,text/csv"
                onChange={handleFileChange}
                className="sr-only"
                id="prod-import-file-input"
              />
              <div className="ui-dropzone">
                <div className="min-w-0 flex-1 space-y-0.5">
                  {selectedFile ? (
                    <>
                      <div className="text-sm font-medium text-foreground break-all">
                        {selectedFile.name}
                      </div>
                      <div className="text-xs text-muted-foreground tabular-nums">
                        {formatFileSize(selectedFile.size)}
                      </div>
                    </>
                  ) : (
                    <>
                      <div className="text-sm font-medium text-foreground">
                        {t.prod.import.dropHint}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {t.prod.import.sizeLimitHint}
                      </div>
                    </>
                  )}
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isUploading}
                  className="min-h-10 shrink-0 sm:min-h-8"
                >
                  {selectedFile
                    ? t.prod.import.changeFile
                    : t.prod.import.selectFile}
                </Button>
              </div>
              {selectedFile && (
                <p className="text-xs text-muted-foreground">
                  {t.prod.import.sizeLimitHint}
                </p>
              )}
            </div>

            <div className="space-y-1.5">
              <Label>{t.prod.import.formatLabel}</Label>
              <div className="flex flex-wrap gap-1.5">
                {formatOptions.map((opt) => {
                  const active = format === opt.value;
                  return (
                    <button
                      key={opt.value}
                      type="button"
                      aria-pressed={active}
                      onClick={() => setFormat(opt.value)}
                      disabled={isUploading}
                      className="ui-filter-chip focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
                    >
                      {opt.label}
                    </button>
                  );
                })}
              </div>
            </div>

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => handleOpenChange(false)}
                disabled={isUploading}
                className="min-h-11 w-full sm:min-h-9 sm:w-auto"
              >
                {t.common.cancel}
              </Button>
              <Button
                type="button"
                onClick={() => void runUpload(false)}
                disabled={
                  !selectedFile ||
                  isUploading ||
                  selectedFile.size > MAX_IMPORT_FILE_BYTES
                }
                className="min-h-11 w-full sm:min-h-9 sm:w-auto"
              >
                {isUploading ? (
                  <>
                    <Loader2 className="size-4 animate-spin" />
                    <span>{t.prod.import.importing}</span>
                  </>
                ) : (
                  <span>{t.prod.import.submit}</span>
                )}
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
