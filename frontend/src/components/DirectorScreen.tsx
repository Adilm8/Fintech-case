"use client";

import { useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Inbox,
  Loader2,
  MessageSquare,
  RefreshCw,
  ShieldCheck,
  X,
  XCircle,
} from "lucide-react";
import { ComparisonTable } from "@/components/ComparisonTable";
import { ReasonsList } from "@/components/ReasonsList";
import { VerdictBadge } from "@/components/VerdictBadge";
import { VerdictBanner } from "@/components/VerdictBanner";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import {
  ApiError,
  decideApproval,
  getErrorMessage,
  isNetworkUnreachableError,
} from "@/lib/api";
import {
  canTrustApproval,
  MIN_DIRECTOR_COMMENT_LENGTH,
} from "@/lib/approvals";
import { formatDateRu, formatKzt } from "@/lib/format";
import type { Approval, ApprovalDecision } from "@/lib/types";
import { cn } from "cn";

interface DirectorScreenProps {
  approvals: Approval[];
  isLoading: boolean;
  onRefresh: () => Promise<void> | void;
  onNetworkError: (message: string) => void;
}

function getFieldFromComparison(approval: Approval, field: string): string {
  const row = approval.check.comparison.find((c) => c.field === field);
  return row?.in_invoice ?? "";
}

function getApprovalSummary(approval: Approval) {
  const recipientName =
    approval.request?.recipient_name ||
    getFieldFromComparison(approval, "name") ||
    "Получатель не указан";
  const recipientBin =
    approval.request?.recipient_bin || getFieldFromComparison(approval, "bin");
  const recipientIik =
    approval.request?.recipient_iik || getFieldFromComparison(approval, "iik");
  const purpose = approval.request?.purpose || "";

  let amountDisplay = "—";
  if (approval.request?.amount_kzt !== undefined) {
    amountDisplay = formatKzt(approval.request.amount_kzt);
  } else {
    const rawAmount = getFieldFromComparison(approval, "amount");
    if (rawAmount) {
      const cleaned = rawAmount.replace(/\s+/g, "").replace(",", ".");
      amountDisplay = Number.isFinite(Number(cleaned))
        ? formatKzt(Number(cleaned))
        : rawAmount;
    }
  }

  return {
    recipientName,
    recipientBin,
    recipientIik,
    purpose,
    amountDisplay,
  };
}

interface PendingApprovalCardProps {
  approval: Approval;
  onDecided: (decision: ApprovalDecision, recipientName: string) => Promise<void>;
  onConflictError: (message: string) => Promise<void>;
  onNetworkError: (message: string) => void;
}

function PendingApprovalCard({
  approval,
  onDecided,
  onConflictError,
  onNetworkError,
}: PendingApprovalCardProps) {
  const [comment, setComment] = useState("");
  const [trustAccount, setTrustAccount] = useState(false);
  const [submittingDecision, setSubmittingDecision] =
    useState<ApprovalDecision | null>(null);
  const [cardError, setCardError] = useState<string | null>(null);

  const summary = getApprovalSummary(approval);
  const isRed = approval.check.verdict === "red";
  const allowTrust = canTrustApproval(approval);
  const effectiveTrust = allowTrust && trustAccount;
  const trimmedComment = comment.trim();
  const commentRequiredForApprove = isRed || effectiveTrust;
  const commentTooShort =
    commentRequiredForApprove &&
    trimmedComment.length < MIN_DIRECTOR_COMMENT_LENGTH;

  const isApproveDisabled = submittingDecision !== null || commentTooShort;

  const handleDecision = async (decision: ApprovalDecision) => {
    setCardError(null);
    setSubmittingDecision(decision);
    try {
      await decideApproval(approval.id, {
        decision,
        director_comment: trimmedComment,
        trust_account: decision === "approved" ? effectiveTrust : false,
      });
      await onDecided(decision, summary.recipientName);
    } catch (err) {
      if (isNetworkUnreachableError(err)) {
        onNetworkError(getErrorMessage(err));
      } else if (err instanceof ApiError && err.status === 409) {
        setCardError(err.message);
        await onConflictError(err.message);
      } else {
        setCardError(getErrorMessage(err));
      }
    } finally {
      setSubmittingDecision(null);
    }
  };

  return (
    <Card className="border-border shadow-xs">
      <CardHeader className="border-b border-border pb-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-1">
            <CardTitle className="text-lg font-semibold">
              {summary.recipientName}
            </CardTitle>
            <CardDescription className="space-y-0.5">
              {(summary.recipientBin || summary.recipientIik) && (
                <div className="font-mono text-xs">
                  {summary.recipientBin ? `БИН ${summary.recipientBin}` : ""}
                  {summary.recipientBin && summary.recipientIik ? " · " : ""}
                  {summary.recipientIik}
                </div>
              )}
              {summary.purpose && (
                <div className="text-sm text-muted-foreground">
                  {summary.purpose}
                </div>
              )}
              {approval.check.history?.compared_with && (
                <div className="inline-block rounded-md border border-amber-200 bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-900">
                  Сравнение с похожим поставщиком:{" "}
                  {approval.check.history.compared_with}
                </div>
              )}
            </CardDescription>
          </div>
          <div className="text-left sm:text-right space-y-1">
            <div className="text-2xl font-bold tabular-nums text-foreground">
              {summary.amountDisplay}
            </div>
            <VerdictBadge verdict={approval.check.verdict} />
          </div>
        </div>
      </CardHeader>

      <CardContent className="pt-5 space-y-5">
        <VerdictBanner
          verdict={approval.check.verdict}
          headlineRu={approval.check.headline_ru}
        />

        <ComparisonTable
          comparison={approval.check.comparison}
          trusted={Boolean(approval.check.trusted)}
        />

        <ReasonsList
          signals={approval.check.signals}
          score={approval.check.score}
        />

        <div className="rounded-xl border border-border bg-muted/40 p-4 space-y-1.5">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            <MessageSquare className="size-3.5" />
            <span>Комментарий бухгалтера</span>
          </div>
          <p className="text-sm text-foreground">
            {approval.accountant_note?.trim()
              ? approval.accountant_note
              : "Бухгалтер не оставил дополнительный комментарий."}
          </p>
        </div>

        <Separator />

        <div className="space-y-4">
          {cardError && (
            <Alert variant="destructive" className="bg-red-50/90 border-red-300">
              <AlertCircle className="size-4" />
              <AlertTitle>Не удалось сохранить решение</AlertTitle>
              <AlertDescription>{cardError}</AlertDescription>
            </Alert>
          )}

          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Label htmlFor={`director-comment-${approval.id}`}>
                Комментарий директора
                {commentRequiredForApprove && (
                  <span className="ml-1 text-red-600 font-semibold">*</span>
                )}
              </Label>
              {commentRequiredForApprove && (
                <span
                  className={cn(
                    "text-xs font-medium tabular-nums",
                    commentTooShort ? "text-red-700" : "text-emerald-700"
                  )}
                >
                  {isRed
                    ? `Обязательно для одобрения (минимум ${MIN_DIRECTOR_COMMENT_LENGTH} символов: ${trimmedComment.length}/${MIN_DIRECTOR_COMMENT_LENGTH})`
                    : `Обязательно для доверенного счёта (минимум ${MIN_DIRECTOR_COMMENT_LENGTH} символов: ${trimmedComment.length}/${MIN_DIRECTOR_COMMENT_LENGTH})`}
                </span>
              )}
            </div>
            <Textarea
              id={`director-comment-${approval.id}`}
              rows={3}
              aria-required={commentRequiredForApprove}
              placeholder={
                commentRequiredForApprove
                  ? `Укажите причину одобрения (не менее ${MIN_DIRECTOR_COMMENT_LENGTH} символов). Для отклонения комментарий не обязателен.`
                  : "Комментарий руководителя (необязательно)..."
              }
              value={comment}
              onChange={(e) => {
                setComment(e.target.value);
                if (cardError) setCardError(null);
              }}
            />
            {commentRequiredForApprove && (
              <p className="text-xs text-muted-foreground">
                Для отклонения платёжной заявки комментарий не требуется.
              </p>
            )}
          </div>

          {allowTrust && (
            <div className="flex items-start gap-2.5 rounded-lg border border-border bg-background px-3.5 py-2.5">
              <Checkbox
                id={`trust-account-${approval.id}`}
                checked={trustAccount}
                onCheckedChange={(checked) => {
                  setTrustAccount(Boolean(checked));
                  if (cardError) setCardError(null);
                }}
                className="mt-0.5"
              />
              <div className="space-y-0.5">
                <Label
                  htmlFor={`trust-account-${approval.id}`}
                  className="cursor-pointer font-medium text-foreground"
                >
                  Доверять этому счёту
                </Label>
                <p className="text-xs text-muted-foreground">
                  После одобрения счёт будет добавлен в доверенные реквизиты
                  поставщика для будущих платежей (требуется комментарий от{" "}
                  {MIN_DIRECTOR_COMMENT_LENGTH} символов).
                </p>
              </div>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-3 pt-1">
            <Button
              type="button"
              size="lg"
              disabled={isApproveDisabled}
              onClick={() => handleDecision("approved")}
              className="gap-2"
            >
              {submittingDecision === "approved" ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  <span>Сохранение...</span>
                </>
              ) : (
                <>
                  <CheckCircle2 className="size-4" />
                  <span>Одобрить</span>
                </>
              )}
            </Button>

            <Button
              type="button"
              variant="destructive"
              size="lg"
              disabled={submittingDecision !== null}
              onClick={() => handleDecision("rejected")}
              className="gap-2"
            >
              {submittingDecision === "rejected" ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  <span>Отклонение...</span>
                </>
              ) : (
                <>
                  <XCircle className="size-4" />
                  <span>Отклонить</span>
                </>
              )}
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export function DirectorScreen({
  approvals,
  isLoading,
  onRefresh,
  onNetworkError,
}: DirectorScreenProps) {
  const [feedback, setFeedback] = useState<{
    decision: ApprovalDecision;
    recipientName: string;
  } | null>(null);
  const [screenError, setScreenError] = useState<string | null>(null);

  const pendingApprovals = approvals.filter((a) => a.status === "pending");
  const resolvedApprovals = approvals.filter((a) => a.status !== "pending");

  const handleDecided = async (
    decision: ApprovalDecision,
    recipientName: string
  ) => {
    setScreenError(null);
    setFeedback({ decision, recipientName });
    await onRefresh();
  };

  const handleConflictError = async (message: string) => {
    setFeedback(null);
    setScreenError(message);
    await onRefresh();
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-foreground">
            Кабинет директора — согласование платежей
          </h1>
          <p className="text-sm text-muted-foreground">
            Рассмотрение платежей, отправленных бухгалтером на дополнительное
            подтверждение.
          </p>
        </div>

        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => void onRefresh()}
          disabled={isLoading}
          className="gap-1.5"
        >
          <RefreshCw className={cn("size-3.5", isLoading && "animate-spin")} />
          <span>Обновить</span>
        </Button>
      </div>

      {screenError && (
        <Alert
          variant="destructive"
          className="bg-red-50/90 border-red-300 pr-10"
        >
          <AlertCircle className="size-4" />
          <AlertTitle>Заявка обновлена</AlertTitle>
          <AlertDescription>{screenError}</AlertDescription>
          <button
            type="button"
            aria-label="Закрыть уведомление"
            onClick={() => setScreenError(null)}
            className="absolute top-2.5 right-2.5 rounded p-1 opacity-70 hover:opacity-100"
          >
            <X className="size-4" />
          </button>
        </Alert>
      )}

      {feedback && (
        <Alert
          className={cn(
            "pr-10",
            feedback.decision === "approved"
              ? "border-emerald-300 bg-emerald-50 text-emerald-950"
              : "border-slate-300 bg-slate-50 text-slate-950"
          )}
        >
          {feedback.decision === "approved" ? (
            <CheckCircle2 className="size-4 text-emerald-600" />
          ) : (
            <XCircle className="size-4 text-slate-600" />
          )}
          <AlertTitle>
            {feedback.decision === "approved"
              ? "Платёж одобрен"
              : "Платёж отклонён"}
          </AlertTitle>
          <AlertDescription>
            Решение по платежу для {feedback.recipientName} сохранено.
          </AlertDescription>
          <button
            type="button"
            aria-label="Закрыть уведомление"
            onClick={() => setFeedback(null)}
            className="absolute top-2.5 right-2.5 rounded p-1 opacity-70 hover:opacity-100"
          >
            <X className="size-4" />
          </button>
        </Alert>
      )}

      {isLoading && approvals.length === 0 ? (
        <Card className="border-border shadow-xs">
          <CardContent className="flex items-center justify-center gap-2.5 py-16 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin text-[var(--brand)]" />
            <span>Загружаем заявки на согласование...</span>
          </CardContent>
        </Card>
      ) : pendingApprovals.length === 0 ? (
        <Card className="border-border shadow-xs">
          <CardContent className="flex flex-col items-center justify-center gap-2.5 py-14 text-center">
            <div className="flex size-11 items-center justify-center rounded-full bg-muted text-muted-foreground">
              <Inbox className="size-5" />
            </div>
            <div className="text-base font-medium text-foreground">
              Нет платежей, ожидающих решения
            </div>
            <p className="max-w-md text-sm text-muted-foreground">
              Когда бухгалтер отправит платёж на согласование, карточка
              проверки появится здесь.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-6">
          {pendingApprovals.map((approval) => (
            <PendingApprovalCard
              key={approval.id}
              approval={approval}
              onDecided={handleDecided}
              onConflictError={handleConflictError}
              onNetworkError={onNetworkError}
            />
          ))}
        </div>
      )}

      {resolvedApprovals.length > 0 && (
        <Card className="border-border shadow-xs">
          <CardHeader className="border-b border-border pb-3.5">
            <CardTitle className="text-base font-semibold">Решённые</CardTitle>
          </CardHeader>
          <CardContent className="divide-y divide-border p-0">
            {resolvedApprovals.map((approval) => {
              const summary = getApprovalSummary(approval);
              const isApproved = approval.status === "approved";

              return (
                <div
                  key={approval.id}
                  className="flex flex-wrap items-center justify-between gap-4 px-5 py-3.5 text-sm"
                >
                  <div className="min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium text-foreground">
                        {summary.recipientName}
                      </span>
                      <span className="font-semibold tabular-nums text-foreground">
                        {summary.amountDisplay}
                      </span>
                    </div>
                    {approval.director_comment && (
                      <p className="text-xs text-muted-foreground">
                        Комментарий директора: {approval.director_comment}
                      </p>
                    )}
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    {approval.trust_account && (
                      <Badge
                        variant="outline"
                        className="gap-1 border-emerald-200 bg-emerald-50 text-emerald-800"
                      >
                        <ShieldCheck className="size-3" />
                        <span>Доверенный счёт</span>
                      </Badge>
                    )}
                    <Badge
                      variant="outline"
                      className={cn(
                        isApproved
                          ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                          : "border-red-200 bg-red-50 text-red-800"
                      )}
                    >
                      {isApproved ? "Одобрено" : "Отклонено"}
                    </Badge>
                    {approval.decided_at && (
                      <span className="text-xs text-muted-foreground">
                        {formatDateRu(approval.decided_at)}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
