"use client";

import { useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  CheckCircle2,
  Loader2,
  Plus,
  Send,
  ShieldCheck,
  Upload,
} from "lucide-react";
import { notifyProdNotificationsUpdated } from "@/components/prod/NotificationBell";
import { notifyProdApprovalsUpdated } from "@/components/prod/ProdShell";
import { Alert, AlertDescription } from "@/components/ui/alert";
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
import { Textarea } from "@/components/ui/textarea";
import { useT } from "@/i18n";
import {
  batchSendToDirector,
  batchSignGreen,
  getProdErrorMessage,
} from "@/lib/prod/api";
import type { BatchActionResult, Role } from "@/lib/prod/types";
import { notify } from "@/lib/toast";

interface BatchToolbarProps {
  role: Role;
  batchId?: string | null;
  greenCount: number;
  sendToDirectorCount: number;
  showBatchActions: boolean;
  onNewPayment: () => void;
  onOpenImport: () => void;
  onBatchCompleted: () => void;
}

type BatchModalKind = "sign-green" | "send-director" | null;

export function BatchToolbar({
  role,
  batchId,
  greenCount,
  sendToDirectorCount,
  showBatchActions,
  onNewPayment,
  onOpenImport,
  onBatchCompleted,
}: BatchToolbarProps) {
  const { t, lang, interpolate } = useT();
  const [activeModal, setActiveModal] = useState<BatchModalKind>(null);
  const [accountantNote, setAccountantNote] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BatchActionResult | null>(null);

  const isAccountant = role === "accountant";
  const canSignBatch = role === "accountant" || role === "director";

  if (!isAccountant && !canSignBatch) {
    return null;
  }

  const openModal = (kind: Exclude<BatchModalKind, null>) => {
    setError(null);
    setResult(null);
    setAccountantNote("");
    setActiveModal(kind);
  };

  const closeModal = (nextOpen: boolean) => {
    if (!nextOpen && isRunning) return;
    if (!nextOpen) {
      setActiveModal(null);
      setError(null);
      setResult(null);
    }
  };

  const handleConfirm = async () => {
    if (!activeModal || isRunning) return;
    setError(null);
    setIsRunning(true);
    try {
      if (activeModal === "sign-green") {
        const res = await batchSignGreen(
          batchId ? { batch_id: batchId } : {},
          lang
        );
        setResult(res);
        onBatchCompleted();
        notifyProdNotificationsUpdated();
        notify.success(
          t.prod.batch.signGreenToastTitle,
          interpolate(t.prod.batch.signGreenToastDesc, {
            done: res.done.length,
            skipped: res.skipped.length,
          })
        );
      } else {
        const note = accountantNote.trim();
        const res = await batchSendToDirector(
          {
            ...(batchId ? { batch_id: batchId } : {}),
            ...(note ? { accountant_note: note } : {}),
          },
          lang
        );
        setResult(res);
        onBatchCompleted();
        notifyProdApprovalsUpdated();
        notify.success(
          t.prod.batch.sendDirectorToastTitle,
          interpolate(t.prod.batch.sendDirectorToastDesc, {
            done: res.done.length,
            skipped: res.skipped.length,
          })
        );
      }
    } catch (err) {
      setError(getProdErrorMessage(err));
    } finally {
      setIsRunning(false);
    }
  };

  if (!isAccountant && !showBatchActions) {
    return null;
  }

  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        {isAccountant && (
          <>
            <Button
              type="button"
              onClick={onNewPayment}
              className="min-h-11 gap-2 rounded-xl px-4 font-semibold shadow-[0_2px_8px_rgba(0,171,117,0.22)] sm:min-h-10"
            >
              <Plus className="size-4" />
              <span>{t.prod.payments.actions.newPayment}</span>
            </Button>

            <Button
              type="button"
              variant="outline"
              onClick={onOpenImport}
              className="min-h-11 gap-2 rounded-xl sm:min-h-10"
            >
              <Upload className="size-4" />
              <span>{t.prod.payments.actions.importFile}</span>
            </Button>
          </>
        )}

        {showBatchActions && canSignBatch && (
          <Button
            type="button"
            variant="outline"
            disabled={greenCount === 0}
            onClick={() => openModal("sign-green")}
            className="min-h-11 gap-2 rounded-xl border-[#00AB75]/40 bg-[#E8F8F2]/60 text-[#006B49] hover:bg-[#E8F8F2] disabled:opacity-50 sm:min-h-10"
          >
            <ShieldCheck className="size-4" />
            <span>
              {interpolate(t.prod.payments.actions.signAllGreen, {
                count: greenCount,
              })}
            </span>
          </Button>
        )}

        {showBatchActions && isAccountant && (
          <Button
            type="button"
            variant="outline"
            disabled={sendToDirectorCount === 0}
            onClick={() => openModal("send-director")}
            className="min-h-11 gap-2 rounded-xl sm:min-h-10"
          >
            <Send className="size-4" />
            <span>
              {interpolate(t.prod.payments.actions.sendRestToDirector, {
                count: sendToDirectorCount,
              })}
            </span>
          </Button>
        )}
      </div>

      <Dialog open={activeModal !== null} onOpenChange={closeModal}>
        <DialogContent mobileSheet className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>
              {activeModal === "sign-green"
                ? t.prod.batch.signGreenTitle
                : t.prod.batch.sendDirectorTitle}
            </DialogTitle>
            {!result && (
              <DialogDescription>
                {activeModal === "sign-green"
                  ? interpolate(t.prod.batch.signGreenDescription, {
                      count: greenCount,
                    })
                  : interpolate(t.prod.batch.sendDirectorDescription, {
                      count: sendToDirectorCount,
                    })}
              </DialogDescription>
            )}
          </DialogHeader>

          {result ? (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                <Badge
                  variant="outline"
                  className="h-auto gap-1.5 border-[#00AB75]/35 bg-[#E8F8F2] px-3 py-1 text-xs font-semibold text-[#006B49]"
                >
                  <CheckCircle2 className="size-3.5" />
                  <span>
                    {interpolate(t.prod.batch.resultDone, {
                      count: result.done.length,
                    })}
                  </span>
                </Badge>
                <Badge
                  variant="outline"
                  className="h-auto px-3 py-1 text-xs font-semibold text-muted-foreground"
                >
                  {interpolate(t.prod.batch.resultSkipped, {
                    count: result.skipped.length,
                  })}
                </Badge>
              </div>

              {result.skipped.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  {t.prod.batch.allDoneMessage}
                </p>
              ) : (
                <div className="space-y-2">
                  <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    {t.prod.batch.skippedListTitle}
                  </div>
                  <div className="max-h-56 space-y-1.5 overflow-y-auto rounded-xl border border-border bg-background/80 p-2.5">
                    {result.skipped.map((item) => (
                      <div
                        key={`${item.id}-${item.code}`}
                        className="rounded-lg border border-border bg-card px-3 py-2 text-xs space-y-1"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <Link
                            href={`/payments/${item.id}`}
                            onClick={() => closeModal(false)}
                            className="font-mono font-semibold text-[var(--brand-text)] hover:underline"
                          >
                            {item.id}
                          </Link>
                          <Badge
                            variant="outline"
                            className="h-auto font-mono text-[10px] text-muted-foreground"
                          >
                            {item.code}
                          </Badge>
                        </div>
                        <p className="text-muted-foreground break-words">
                          {item.detail}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <DialogFooter>
                <Button
                  type="button"
                  onClick={() => closeModal(false)}
                  className="min-h-11 w-full sm:min-h-10 sm:w-auto"
                >
                  {t.prod.batch.doneButton}
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

              {activeModal === "send-director" && (
                <div className="space-y-1.5">
                  <Label htmlFor="batch-director-note">
                    {t.prod.batch.sendDirectorNoteLabel}
                  </Label>
                  <Textarea
                    id="batch-director-note"
                    rows={3}
                    maxLength={1000}
                    placeholder={t.prod.batch.sendDirectorNotePlaceholder}
                    value={accountantNote}
                    onChange={(e) => setAccountantNote(e.target.value)}
                    disabled={isRunning}
                    className="min-h-20"
                  />
                </div>
              )}

              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => closeModal(false)}
                  disabled={isRunning}
                  className="min-h-11 w-full sm:min-h-10 sm:w-auto"
                >
                  {t.common.cancel}
                </Button>
                <Button
                  type="button"
                  onClick={() => void handleConfirm()}
                  disabled={isRunning}
                  className="min-h-11 w-full gap-2 sm:min-h-10 sm:w-auto"
                >
                  {isRunning ? (
                    <>
                      <Loader2 className="size-4 animate-spin" />
                      <span>
                        {activeModal === "sign-green"
                          ? t.prod.batch.signing
                          : t.prod.batch.sending}
                      </span>
                    </>
                  ) : activeModal === "sign-green" ? (
                    <>
                      <ShieldCheck className="size-4" />
                      <span>{t.prod.batch.signGreenConfirm}</span>
                    </>
                  ) : (
                    <>
                      <Send className="size-4" />
                      <span>{t.prod.batch.sendDirectorConfirm}</span>
                    </>
                  )}
                </Button>
              </DialogFooter>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
