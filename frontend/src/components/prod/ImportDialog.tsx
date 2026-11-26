"use client";

import { useRef, useState, type ChangeEvent } from "react";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  FileSpreadsheet,
  FolderOpen,
  Loader2,
  Upload,
} from "lucide-react";
import { VerdictBadge } from "@/components/VerdictBadge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
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
          <DialogTitle className="text-lg">{t.prod.import.title}</DialogTitle>
          <DialogDescription>{t.prod.import.description}</DialogDescription>
        </DialogHeader>

        {result ? (
          <div className="space-y-4">
            <div className="flex items-center gap-2 rounded-xl border border-[#00AB75]/35 bg-[#E8F8F2] px-3.5 py-2.5 text-sm font-medium text-[#064A34]">
              <CheckCircle2 className="size-4 shrink-0 text-[var(--brand-text)]" />
              <span className="truncate">
                {result.batch.filename} ({result.batch.source.toUpperCase()})
              </span>
            </div>

            <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
              <div className="rounded-xl border border-border bg-background/80 p-3">
                <div className="text-xs text-muted-foreground">
                  {t.prod.import.statTotal}
                </div>
                <div className="mt-1 text-xl font-bold tabular-nums">
                  {result.summary.total}
                </div>
              </div>
              <div className="rounded-xl border border-border bg-background/80 p-3">
                <div className="text-xs text-muted-foreground">
                  {t.prod.import.statCreated}
                </div>
                <div className="mt-1 text-xl font-bold tabular-nums text-[var(--brand-text)]">
                  {result.summary.created}
                </div>
              </div>
              <div className="rounded-xl border border-border bg-background/80 p-3">
                <div className="text-xs text-muted-foreground">
                  {t.prod.import.statFailed}
                </div>
                <div
                  className={cn(
                    "mt-1 text-xl font-bold tabular-nums",
                    result.summary.failed > 0 ? "text-red-700" : "text-foreground"
                  )}
                >
                  {result.summary.failed}
                </div>
              </div>
              <div className="rounded-xl border border-border bg-background/80 p-3">
                <div className="text-xs text-muted-foreground">
                  {t.prod.import.statDuplicates}
                </div>
                <div
                  className={cn(
                    "mt-1 text-xl font-bold tabular-nums",
                    result.summary.duplicates > 0
                      ? "text-amber-700"
                      : "text-foreground"
                  )}
                >
                  {result.summary.duplicates}
                </div>
              </div>
            </div>

            <div className="space-y-2">
              <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {t.prod.import.verdictBreakdown}
              </div>
              <div className="flex flex-wrap gap-2">
                {VERDICT_ORDER.map((v) => {
                  const count = result.summary.by_verdict[v] ?? 0;
                  if (count === 0) return null;
                  return (
                    <VerdictBadge
                      key={v}
                      verdict={v}
                      label={`${t.verdicts[v]}: ${count}`}
                    />
                  );
                })}
              </div>
            </div>

            {result.errors.length > 0 && (
              <div className="space-y-2">
                <div className="text-xs font-semibold uppercase tracking-wide text-red-800">
                  {interpolate(t.prod.import.errorsTitle, {
                    count: result.errors.length,
                  })}
                </div>
                <div className="max-h-48 space-y-1.5 overflow-y-auto rounded-xl border border-border bg-background/80 p-2.5">
                  {result.errors.map((errItem, idx) => (
                    <div
                      key={`${errItem.code}-${errItem.line_no ?? "x"}-${idx}`}
                      className="rounded-lg border border-border bg-card px-3 py-2 text-xs space-y-0.5"
                    >
                      <div className="flex flex-wrap items-center gap-1.5 font-medium text-foreground">
                        {errItem.line_no !== null && (
                          <Badge
                            variant="outline"
                            className="h-auto px-1.5 py-0 text-[11px] font-mono"
                          >
                            {interpolate(t.prod.import.linePrefix, {
                              line: errItem.line_no,
                            })}
                          </Badge>
                        )}
                        {errItem.doc_number && (
                          <Badge
                            variant="secondary"
                            className="h-auto px-1.5 py-0 text-[11px]"
                          >
                            {interpolate(t.prod.import.docPrefix, {
                              doc: errItem.doc_number,
                            })}
                          </Badge>
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
                className="min-h-11 w-full sm:min-h-10 sm:w-auto"
              >
                {t.prod.import.importAnother}
              </Button>
              <Button
                type="button"
                onClick={handleOpenBatch}
                className="min-h-11 w-full gap-2 sm:min-h-10 sm:w-auto"
              >
                <FolderOpen className="size-4" />
                <span>{t.prod.import.openBatchButton}</span>
              </Button>
            </DialogFooter>
          </div>
        ) : (
          <div className="space-y-4">
            {error && (
              <Alert
                variant="destructive"
                className="border-red-300 bg-red-50/90"
              >
                <AlertCircle className="size-4" />
                <AlertDescription className="break-words">
                  {error}
                </AlertDescription>
              </Alert>
            )}

            {duplicatePrompt && (
              <Alert className="border-amber-300 bg-amber-50/95 text-amber-950">
                <AlertTriangle className="size-4 text-amber-700" />
                <AlertTitle>{t.prod.import.duplicateTitle}</AlertTitle>
                <AlertDescription className="space-y-3 text-amber-900">
                  <p>{t.prod.import.duplicateDescription}</p>
                  <Button
                    type="button"
                    size="sm"
                    onClick={() => void runUpload(true)}
                    disabled={isUploading}
                    className="min-h-10 gap-2 bg-amber-600 text-white hover:bg-amber-700 sm:min-h-8"
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
                </AlertDescription>
              </Alert>
            )}

            <div className="space-y-2">
              <input
                ref={fileInputRef}
                type="file"
                accept=".txt,.csv,text/plain,text/csv"
                onChange={handleFileChange}
                className="sr-only"
                id="prod-import-file-input"
              />
              <label
                htmlFor="prod-import-file-input"
                className={cn(
                  "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-4 py-7 text-center transition-colors",
                  selectedFile
                    ? "border-primary/50 bg-accent/40"
                    : "border-border bg-background/60 hover:border-primary/40 hover:bg-muted/40"
                )}
              >
                <div className="flex size-11 items-center justify-center rounded-xl bg-accent text-[var(--brand-text)]">
                  <FileSpreadsheet className="size-5" />
                </div>
                {selectedFile ? (
                  <div className="space-y-0.5">
                    <div className="text-sm font-semibold text-foreground break-all">
                      {selectedFile.name}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {formatFileSize(selectedFile.size)} ·{" "}
                      {t.prod.import.changeFile}
                    </div>
                  </div>
                ) : (
                  <div className="space-y-0.5">
                    <div className="text-sm font-medium text-foreground">
                      {t.prod.import.dropHint}
                    </div>
                    <div className="text-xs text-[var(--brand-text)] font-medium">
                      {t.prod.import.selectFile}
                    </div>
                  </div>
                )}
              </label>
              <p className="text-xs text-muted-foreground">
                {t.prod.import.sizeLimitHint}
              </p>
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
                      className={cn(
                        "inline-flex min-h-10 cursor-pointer items-center rounded-xl border px-3 py-1.5 text-xs font-medium transition-all sm:min-h-8",
                        active
                          ? "border-primary bg-accent text-accent-foreground font-semibold"
                          : "border-border bg-card text-muted-foreground hover:bg-muted/60 hover:text-foreground"
                      )}
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
                className="min-h-11 w-full sm:min-h-10 sm:w-auto"
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
                className="min-h-11 w-full gap-2 sm:min-h-10 sm:w-auto"
              >
                {isUploading ? (
                  <>
                    <Loader2 className="size-4 animate-spin" />
                    <span>{t.prod.import.importing}</span>
                  </>
                ) : (
                  <>
                    <Upload className="size-4" />
                    <span>{t.prod.import.submit}</span>
                  </>
                )}
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
