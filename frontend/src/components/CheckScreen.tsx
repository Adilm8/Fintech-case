"use client";

import { useState } from "react";
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  Clock,
  FileEdit,
  Loader2,
  PauseCircle,
  RefreshCw,
  Send,
  ShieldCheck,
  X,
  XCircle,
} from "lucide-react";
import { AdviceBox } from "@/components/AdviceBox";
import { ComparisonTable } from "@/components/ComparisonTable";
import { ReasonsList } from "@/components/ReasonsList";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
import { VerdictBanner } from "@/components/VerdictBanner";
import {
  checkPayment,
  createApproval,
  getErrorMessage,
  isNetworkUnreachableError,
} from "@/lib/api";
import {
  APPROVAL_STATUS_META,
  findApprovalForPayment,
} from "@/lib/approvals";
import {
  formatDateRu,
  formatKzt,
  formatTrustedBannerText,
} from "@/lib/format";
import type { Approval, CheckRequest, CheckResult } from "@/lib/types";
import { cn } from "cn";

interface CheckScreenProps {
  request: CheckRequest;
  result: CheckResult;
  approvals: Approval[];
  onBack: () => void;
  onFixRequisites?: (request: CheckRequest) => void;
  onResultUpdate?: (updatedResult: CheckResult) => void;
  onApprovalCreated?: (approval: Approval) => void;
  onNetworkError?: (message: string) => void;
}

interface ToastState {
  tone: "success" | "warning";
  title: string;
  description: string;
}

export function CheckScreen({
  request,
  result,
  approvals,
  onBack,
  onFixRequisites,
  onResultUpdate,
  onApprovalCreated,
  onNetworkError,
}: CheckScreenProps) {
  const [override, setOverride] = useState<{
    baseCheckId: string;
    result: CheckResult;
  } | null>(null);
  const currentResult =
    override && override.baseCheckId === result.check_id
      ? override.result
      : result;

  const [isRechecking, setIsRechecking] = useState(false);
  const [toast, setToast] = useState<ToastState | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [accountantNote, setAccountantNote] = useState("");
  const [isSendingApproval, setIsSendingApproval] = useState(false);
  const [dialogError, setDialogError] = useState<string | null>(null);

  const [sentApprovalId, setSentApprovalId] = useState<string | null>(null);
  const [localApproval, setLocalApproval] = useState<Approval | null>(null);

  const matchedApproval = findApprovalForPayment(approvals, request);
  const effectiveApproval = matchedApproval ?? localApproval;
  const approvalStatus =
    effectiveApproval?.status ?? (sentApprovalId ? "pending" : null);

  const isPendingApproval = approvalStatus === "pending";
  const isApprovedByDirector = approvalStatus === "approved";
  const isRejectedByDirector = approvalStatus === "rejected";
  const isTrusted = currentResult.trusted === true;
  const showTrustedBanner = isTrusted || Boolean(currentResult.trusted_info);

  const handleRecheck = async () => {
    setIsRechecking(true);
    setActionError(null);
    try {
      const updated = await checkPayment(request);
      setOverride({ baseCheckId: result.check_id, result: updated });
      onResultUpdate?.(updated);
      setToast({
        tone: "success",
        title: "Проверка обновлена",
        description:
          "Реквизиты и история платежей перепроверены по актуальным данным.",
      });
    } catch (err) {
      if (isNetworkUnreachableError(err)) {
        onNetworkError?.(getErrorMessage(err));
      } else {
        setActionError(getErrorMessage(err));
      }
    } finally {
      setIsRechecking(false);
    }
  };

  const handleSignDemo = () => {
    setActionError(null);
    setToast({
      tone: "success",
      title: "Платёж подписан (демо)",
      description: `Платёж на сумму ${formatKzt(
        request.amount_kzt
      )} в пользу ${request.recipient_name} передан в исполнение.`,
    });
  };

  const handlePostponeDemo = () => {
    setActionError(null);
    setToast({
      tone: "warning",
      title: "Платёж отложен на проверку",
      description:
        "Платёж снят с подписания до подтверждения реквизитов у поставщика.",
    });
  };

  const handleSendToDirector = async () => {
    if (isSendingApproval || isPendingApproval || sentApprovalId !== null) {
      return;
    }

    setDialogError(null);
    setIsSendingApproval(true);
    try {
      const created = await createApproval({
        request,
        accountant_note: accountantNote.trim(),
      });
      setSentApprovalId(created.id);
      setLocalApproval(created);
      setDialogOpen(false);
      setAccountantNote("");
      onApprovalCreated?.(created);
      setToast({
        tone: "success",
        title: "Отправлено директору",
        description:
          "Заявка на согласование появилась в кабинете директора. Вы можете переключить роль в шапке, чтобы рассмотреть её.",
      });
    } catch (err) {
      if (isNetworkUnreachableError(err)) {
        setDialogOpen(false);
        onNetworkError?.(getErrorMessage(err));
      } else {
        setDialogError(getErrorMessage(err));
      }
    } finally {
      setIsSendingApproval(false);
    }
  };

  const verdict = currentResult.verdict;
  const approvalMeta = effectiveApproval
    ? APPROVAL_STATUS_META[effectiveApproval.status]
    : approvalStatus
      ? APPROVAL_STATUS_META[approvalStatus]
      : null;
  const directorComment = effectiveApproval?.director_comment?.trim() || null;

  const openDirectorDialog = () => {
    if (isPendingApproval || sentApprovalId !== null) {
      return;
    }
    setDialogError(null);
    setDialogOpen(true);
  };

  const renderActionButtons = () => {
    if (verdict === "invalid") {
      return (
        <Button
          type="button"
          size="lg"
          onClick={() =>
            onFixRequisites ? onFixRequisites(request) : onBack()
          }
          className="w-full gap-2 bg-orange-600 text-white hover:bg-orange-700"
        >
          <FileEdit className="size-4" />
          <span>Исправить реквизиты</span>
        </Button>
      );
    }

    if (isRejectedByDirector) {
      return (
        <div className="rounded-lg border border-red-300 bg-red-50 p-3.5 text-sm text-red-950 space-y-1">
          <div className="flex items-center gap-2 font-semibold text-red-800">
            <XCircle className="size-4 shrink-0" />
            <span>Платёж отклонён директором</span>
          </div>
          {directorComment && (
            <p className="text-xs text-red-900">
              Комментарий директора: {directorComment}
            </p>
          )}
        </div>
      );
    }

    if (isApprovedByDirector) {
      return (
        <div className="space-y-2">
          <Button
            type="button"
            size="lg"
            onClick={handleSignDemo}
            className="w-full gap-2"
          >
            <ShieldCheck className="size-4" />
            <span>Подписать</span>
          </Button>
          <p className="text-xs text-emerald-800">
            Согласовано директором — подписание платежа разрешено.
          </p>
        </div>
      );
    }

    if (isPendingApproval) {
      if (verdict === "red") {
        return (
          <div className="space-y-2">
            <Button
              type="button"
              size="lg"
              onClick={handlePostponeDemo}
              className="w-full gap-2 bg-red-600 text-white hover:bg-red-700"
            >
              <PauseCircle className="size-4" />
              <span>Отложить и проверить</span>
            </Button>
            <Button
              type="button"
              variant="outline"
              size="lg"
              disabled
              className="w-full gap-2"
            >
              <Clock className="size-4" />
              <span>Отправлено директору</span>
            </Button>
            <p className="pt-1 text-xs text-muted-foreground">
              Подписание платежа заблокировано до решения директора.
            </p>
          </div>
        );
      }

      if (verdict === "green") {
        return (
          <div className="space-y-2">
            <Button
              type="button"
              size="lg"
              onClick={handleSignDemo}
              className="w-full gap-2"
            >
              <ShieldCheck className="size-4" />
              <span>Подписать</span>
            </Button>
            <Button
              type="button"
              variant="outline"
              size="lg"
              disabled
              className="w-full gap-2"
            >
              <Clock className="size-4" />
              <span>Отправлено директору</span>
            </Button>
          </div>
        );
      }

      return (
        <div className="space-y-2">
          <Button
            type="button"
            size="lg"
            disabled
            className="w-full gap-2"
          >
            <Clock className="size-4" />
            <span>Отправлено директору</span>
          </Button>
          <Button
            type="button"
            variant="outline"
            size="lg"
            onClick={handleSignDemo}
            className="w-full gap-2"
          >
            <ShieldCheck className="size-4" />
            <span>Подписать</span>
          </Button>
        </div>
      );
    }

    if (verdict === "green") {
      return (
        <Button
          type="button"
          size="lg"
          onClick={handleSignDemo}
          className="w-full gap-2"
        >
          <ShieldCheck className="size-4" />
          <span>Подписать</span>
        </Button>
      );
    }

    if (verdict === "red") {
      return (
        <div className="space-y-2">
          <Button
            type="button"
            size="lg"
            onClick={handlePostponeDemo}
            className="w-full gap-2 bg-red-600 text-white hover:bg-red-700"
          >
            <PauseCircle className="size-4" />
            <span>Отложить и проверить</span>
          </Button>
          <Button
            type="button"
            variant="outline"
            size="lg"
            onClick={openDirectorDialog}
            className="w-full gap-2"
          >
            <Send className="size-4" />
            <span>Отправить директору</span>
          </Button>
          <p className="pt-1 text-xs text-muted-foreground">
            Подписание платежа заблокировано до проверки или согласования
            директором.
          </p>
        </div>
      );
    }

    return (
      <div className="space-y-2">
        <Button
          type="button"
          size="lg"
          onClick={openDirectorDialog}
          className="w-full gap-2"
        >
          <Send className="size-4" />
          <span>Отправить директору</span>
        </Button>
        <Button
          type="button"
          variant="outline"
          size="lg"
          onClick={handleSignDemo}
          className="w-full gap-2"
        >
          <ShieldCheck className="size-4" />
          <span>Подписать</span>
        </Button>
      </div>
    );
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={onBack}
          className="gap-1.5 text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" />
          <span>Назад к списку</span>
        </Button>

        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={handleRecheck}
          disabled={isRechecking}
          className="gap-1.5"
        >
          <RefreshCw
            className={cn("size-3.5", isRechecking && "animate-spin")}
          />
          <span>{isRechecking ? "Перепроверка..." : "Перепроверить"}</span>
        </Button>
      </div>

      {toast && (
        <Alert
          className={cn(
            "pr-10",
            toast.tone === "success"
              ? "border-emerald-300 bg-emerald-50 text-emerald-950"
              : "border-amber-300 bg-amber-50 text-amber-950"
          )}
        >
          {toast.tone === "success" ? (
            <CheckCircle2 className="size-4 text-emerald-600" />
          ) : (
            <PauseCircle className="size-4 text-amber-600" />
          )}
          <AlertTitle>{toast.title}</AlertTitle>
          <AlertDescription
            className={
              toast.tone === "success" ? "text-emerald-900" : "text-amber-900"
            }
          >
            {toast.description}
          </AlertDescription>
          <button
            type="button"
            aria-label="Закрыть уведомление"
            onClick={() => setToast(null)}
            className="absolute top-2.5 right-2.5 rounded p-1 opacity-70 hover:opacity-100"
          >
            <X className="size-4" />
          </button>
        </Alert>
      )}

      {actionError && (
        <Alert variant="destructive" className="bg-red-50/90 border-red-300">
          <AlertCircle className="size-4" />
          <AlertTitle>Не удалось выполнить действие</AlertTitle>
          <AlertDescription>{actionError}</AlertDescription>
        </Alert>
      )}

      <Card className="border-border shadow-xs">
        <CardContent className="flex flex-wrap items-center justify-between gap-4 py-4">
          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Платёжное поручение на проверку
              </span>
              {approvalMeta && (
                <Badge
                  variant="outline"
                  className={cn(
                    "px-2 py-0.5 text-xs font-medium",
                    approvalMeta.badgeClass
                  )}
                >
                  {approvalMeta.labelRu}
                </Badge>
              )}
            </div>
            <div className="text-lg font-semibold text-foreground">
              {request.recipient_name}
            </div>
            <div className="text-sm text-muted-foreground">
              {request.purpose}
            </div>
            {directorComment && (
              <div className="rounded-md border border-border bg-muted/50 px-3 py-1.5 text-xs text-foreground">
                <span className="font-semibold">Комментарий директора: </span>
                <span>{directorComment}</span>
              </div>
            )}
          </div>

          <div className="text-left sm:text-right space-y-1">
            <div className="text-2xl font-bold tabular-nums text-foreground">
              {formatKzt(request.amount_kzt)}
            </div>
            <div className="text-xs text-muted-foreground space-y-1">
              <div>
                {(currentResult.history?.payments_count ?? 0) > 0
                  ? `В истории платежей: ${currentResult.history.payments_count} · последний ${formatDateRu(
                      currentResult.history.last_payment_date
                    )}`
                  : "Ранее платежей этому получателю не было"}
              </div>
              {currentResult.history?.compared_with && (
                <div className="inline-block rounded-md border border-amber-200 bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-900">
                  Сравнение с похожим поставщиком:{" "}
                  {currentResult.history.compared_with}
                </div>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      <VerdictBanner
        verdict={verdict}
        headlineRu={currentResult.headline_ru}
      />

      {showTrustedBanner && (
        <Alert className="border-emerald-300 bg-emerald-50 text-emerald-950">
          <ShieldCheck className="size-4 text-emerald-600" />
          <AlertTitle>Счёт в списке доверенных</AlertTitle>
          <AlertDescription className="text-emerald-900 font-medium">
            {formatTrustedBannerText(currentResult.trusted_info)}
          </AlertDescription>
        </Alert>
      )}

      {isRejectedByDirector && (
        <Alert className="border-red-300 bg-red-50 text-red-950">
          <XCircle className="size-4 text-red-600" />
          <AlertTitle>Платёж отклонён директором</AlertTitle>
          <AlertDescription className="text-red-900">
            {directorComment
              ? `Комментарий директора: ${directorComment}`
              : "Подписание и повторная отправка этого платежа заблокированы."}
          </AlertDescription>
        </Alert>
      )}

      <ComparisonTable
        comparison={currentResult.comparison}
        trusted={isTrusted}
      />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_380px] items-start">
        <ReasonsList
          signals={currentResult.signals}
          score={currentResult.score}
        />

        <div className="space-y-4">
          <AdviceBox
            textRu={currentResult.next_action.text_ru}
            verdict={verdict}
          />

          <Card className="border-border shadow-xs">
            <CardContent className="pt-4 space-y-2.5">
              <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Действия по платежу
              </div>
              {renderActionButtons()}
            </CardContent>
          </Card>
        </div>
      </div>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Отправить платёж директору</DialogTitle>
            <DialogDescription>
              Укажите комментарий для руководителя: например, звонили ли вы
              поставщику и почему счёт изменился.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3 py-1">
            {dialogError && (
              <Alert variant="destructive">
                <AlertCircle className="size-4" />
                <AlertDescription>{dialogError}</AlertDescription>
              </Alert>
            )}

            <div className="rounded-lg border border-border bg-muted/40 px-3 py-2 text-xs space-y-0.5">
              <div className="font-medium text-foreground">
                {request.recipient_name}
              </div>
              <div className="text-muted-foreground">
                {formatKzt(request.amount_kzt)} · {request.recipient_iik}
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="accountant_note">Комментарий бухгалтера</Label>
              <Textarea
                id="accountant_note"
                rows={3}
                placeholder="Например: поставщик прислал письмо о смене счёта, прошу подтвердить..."
                value={accountantNote}
                onChange={(e) => setAccountantNote(e.target.value)}
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setDialogOpen(false)}
              disabled={isSendingApproval}
            >
              Отмена
            </Button>
            <Button
              type="button"
              onClick={handleSendToDirector}
              disabled={
                isSendingApproval ||
                isPendingApproval ||
                sentApprovalId !== null
              }
              className="gap-1.5"
            >
              {isSendingApproval ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  <span>Отправка...</span>
                </>
              ) : (
                <>
                  <Send className="size-4" />
                  <span>Отправить</span>
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
