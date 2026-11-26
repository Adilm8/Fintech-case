"use client";

import { useState, type FormEvent } from "react";
import {
  AlertCircle,
  ChevronRight,
  FileText,
  Loader2,
  PlusCircle,
  SearchCheck,
} from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { VerdictBadge } from "@/components/VerdictBadge";
import {
  checkPayment,
  getErrorMessage,
  isNetworkUnreachableError,
} from "@/lib/api";
import {
  APPROVAL_STATUS_META,
  findApprovalForPayment,
} from "@/lib/approvals";
import { formatKzt } from "@/lib/format";
import type {
  Approval,
  CheckRequest,
  CheckResult,
  QueueItem,
} from "@/lib/types";
import { cn } from "cn";

interface PaymentQueueScreenProps {
  queue: QueueItem[];
  approvals: Approval[];
  isLoading: boolean;
  hasError?: boolean;
  prefillRequest?: CheckRequest | null;
  onSelectPayment: (request: CheckRequest, result: CheckResult) => void;
  onNetworkError: (message: string) => void;
}

interface FormState {
  recipient_name: string;
  recipient_bin: string;
  recipient_iik: string;
  recipient_bik: string;
  amount_kzt: string;
  purpose: string;
}

const EMPTY_FORM: FormState = {
  recipient_name: "",
  recipient_bin: "",
  recipient_iik: "",
  recipient_bik: "",
  amount_kzt: "",
  purpose: "",
};

function sanitizeBin(value: string): string {
  return value.replace(/\s+/g, "").replace(/\D+/g, "");
}

function sanitizeCode(value: string): string {
  return value.replace(/\s+/g, "").toUpperCase();
}

function requestToFormState(req: CheckRequest): FormState {
  return {
    recipient_name: req.recipient_name,
    recipient_bin: sanitizeBin(req.recipient_bin),
    recipient_iik: sanitizeCode(req.recipient_iik),
    recipient_bik: sanitizeCode(req.recipient_bik),
    amount_kzt: String(req.amount_kzt),
    purpose: req.purpose,
  };
}

export function PaymentQueueScreen({
  queue,
  approvals,
  isLoading,
  hasError = false,
  prefillRequest,
  onSelectPayment,
  onNetworkError,
}: PaymentQueueScreenProps) {
  const [form, setForm] = useState<FormState>(() =>
    prefillRequest ? requestToFormState(prefillRequest) : EMPTY_FORM
  );
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const updateField = (field: keyof FormState, rawValue: string) => {
    let value = rawValue;
    if (field === "recipient_bin") {
      value = sanitizeBin(rawValue);
    } else if (field === "recipient_iik" || field === "recipient_bik") {
      value = sanitizeCode(rawValue);
    }
    setForm((prev) => ({ ...prev, [field]: value }));
    if (formError) setFormError(null);
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setFormError(null);

    const recipient_name = form.recipient_name.trim();
    const recipient_bin = sanitizeBin(form.recipient_bin);
    const recipient_iik = sanitizeCode(form.recipient_iik);
    const recipient_bik = sanitizeCode(form.recipient_bik);
    const purpose = form.purpose.trim();
    const parsedAmount = Number(
      form.amount_kzt.replace(/\s+/g, "").replace(",", ".")
    );

    setForm((prev) => ({
      ...prev,
      recipient_bin,
      recipient_iik,
      recipient_bik,
    }));

    if (
      !recipient_name ||
      !recipient_bin ||
      !recipient_iik ||
      !recipient_bik ||
      !purpose
    ) {
      setFormError("Заполните все реквизиты платежа перед проверкой.");
      return;
    }

    if (!Number.isFinite(parsedAmount) || parsedAmount <= 0) {
      setFormError("Укажите корректную сумму платежа больше нуля.");
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
    };

    setIsSubmitting(true);
    try {
      const result = await checkPayment(payload);
      onSelectPayment(payload, result);
    } catch (err) {
      if (isNetworkUnreachableError(err)) {
        onNetworkError(getErrorMessage(err));
      } else {
        setFormError(getErrorMessage(err));
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_400px] items-start">
      <Card className="border-border shadow-xs">
        <CardHeader className="border-b border-border pb-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <CardTitle className="flex items-center gap-2 text-lg font-semibold">
                <FileText className="size-5 text-[var(--brand)]" />
                <span>Платежи на подпись</span>
              </CardTitle>
              <CardDescription className="mt-1">
                Нажмите на платёж, чтобы посмотреть результаты проверки
                реквизитов и истории расчётов перед подписанием.
              </CardDescription>
            </div>
            <div className="text-xs font-medium text-muted-foreground tabular-nums">
              {isLoading
                ? "Загрузка..."
                : hasError && queue.length === 0
                  ? "Нет связи с сервером"
                  : `Всего в очереди: ${queue.length}`}
            </div>
          </div>
        </CardHeader>

        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex items-center justify-center gap-2.5 py-16 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin text-[var(--brand)]" />
              <span>Загружаем очередь платежей...</span>
            </div>
          ) : hasError && queue.length === 0 ? (
            <div className="py-12 px-6 text-center text-sm text-muted-foreground">
              Не удалось загрузить список платежей. Проверьте соединение с
              сервером и нажмите «Повторить».
            </div>
          ) : queue.length === 0 ? (
            <div className="py-16 text-center text-sm text-muted-foreground">
              Очередь платежей пуста. Создайте новый платёж в форме справа или
              нажмите «Сбросить демо».
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/40 hover:bg-muted/40">
                  <TableHead className="pl-5">Получатель</TableHead>
                  <TableHead className="text-right">Сумма</TableHead>
                  <TableHead>Назначение</TableHead>
                  <TableHead>Результат проверки</TableHead>
                  <TableHead className="w-10 pr-4" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {queue.map((item) => {
                  const approval = findApprovalForPayment(
                    approvals,
                    item.request
                  );
                  const approvalMeta = approval
                    ? APPROVAL_STATUS_META[approval.status]
                    : null;
                  const directorComment = approval?.director_comment?.trim();

                  return (
                    <TableRow
                      key={item.id}
                      tabIndex={0}
                      role="button"
                      onClick={() => onSelectPayment(item.request, item.result)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          onSelectPayment(item.request, item.result);
                        }
                      }}
                      className="cursor-pointer transition-colors hover:bg-muted/60 focus-visible:bg-muted/60 focus-visible:outline-none"
                    >
                      <TableCell className="pl-5 py-3.5 whitespace-normal">
                        <div className="font-medium text-foreground">
                          {item.request.recipient_name}
                        </div>
                        <div className="mt-0.5 font-mono text-xs text-muted-foreground">
                          БИН {item.request.recipient_bin} ·{" "}
                          {item.request.recipient_iik}
                        </div>
                      </TableCell>
                      <TableCell className="py-3.5 text-right font-semibold tabular-nums text-foreground">
                        {formatKzt(item.request.amount_kzt)}
                      </TableCell>
                      <TableCell className="py-3.5 max-w-xs whitespace-normal text-muted-foreground">
                        <span className="line-clamp-2">
                          {item.request.purpose}
                        </span>
                      </TableCell>
                      <TableCell className="py-3.5 whitespace-normal">
                        <div className="flex flex-col items-start gap-1.5">
                          <VerdictBadge verdict={item.result.verdict} />
                          {approvalMeta && (
                            <Badge
                              variant="outline"
                              className={cn(
                                "px-2 py-0.5 text-[11px] font-medium",
                                approvalMeta.badgeClass
                              )}
                            >
                              {approvalMeta.labelRu}
                            </Badge>
                          )}
                          {directorComment && (
                            <p className="max-w-[220px] line-clamp-2 text-xs text-muted-foreground">
                              Директор: {directorComment}
                            </p>
                          )}
                        </div>
                      </TableCell>
                      <TableCell className="pr-4 py-3.5 text-right text-muted-foreground">
                        <ChevronRight className="ml-auto size-4" />
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card className="border-border shadow-xs">
        <CardHeader className="border-b border-border pb-4">
          <CardTitle className="flex items-center gap-2 text-base font-semibold">
            <PlusCircle className="size-4 text-[var(--brand)]" />
            <span>Новый платёж</span>
          </CardTitle>
          <CardDescription className="mt-1">
            Проверьте произвольные реквизиты поставщика до отправки на подпись.
          </CardDescription>
        </CardHeader>

        <CardContent className="pt-4">
          <form onSubmit={handleSubmit} className="space-y-3.5">
            {formError && (
              <Alert variant="destructive">
                <AlertCircle className="size-4" />
                <AlertDescription>{formError}</AlertDescription>
              </Alert>
            )}

            <div className="space-y-1.5">
              <Label htmlFor="recipient_name">Наименование получателя</Label>
              <Input
                id="recipient_name"
                placeholder='ТОО "СтройСнаб Сервис"'
                value={form.recipient_name}
                onChange={(e) => updateField("recipient_name", e.target.value)}
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="recipient_bin">БИН / ИИН</Label>
                <Input
                  id="recipient_bin"
                  inputMode="numeric"
                  placeholder="180540012345"
                  className="font-mono"
                  value={form.recipient_bin}
                  onChange={(e) => updateField("recipient_bin", e.target.value)}
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="recipient_bik">БИК банка</Label>
                <Input
                  id="recipient_bik"
                  placeholder="KCJBKZKX"
                  className="font-mono uppercase"
                  value={form.recipient_bik}
                  onChange={(e) => updateField("recipient_bik", e.target.value)}
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="recipient_iik">ИИК (счёт получателя)</Label>
              <Input
                id="recipient_iik"
                placeholder="KZ86125KZT5004100100"
                className="font-mono uppercase"
                value={form.recipient_iik}
                onChange={(e) => updateField("recipient_iik", e.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="amount_kzt">Сумма, ₸</Label>
              <Input
                id="amount_kzt"
                type="number"
                min="1"
                step="any"
                placeholder="450000"
                className="tabular-nums"
                value={form.amount_kzt}
                onChange={(e) => updateField("amount_kzt", e.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="purpose">Назначение платежа</Label>
              <Input
                id="purpose"
                placeholder="Оплата за строительные материалы по счёту №14"
                value={form.purpose}
                onChange={(e) => updateField("purpose", e.target.value)}
              />
            </div>

            <Button
              type="submit"
              className="w-full gap-2"
              disabled={isSubmitting}
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  <span>Проверяем реквизиты...</span>
                </>
              ) : (
                <>
                  <SearchCheck className="size-4" />
                  <span>Проверить платёж</span>
                </>
              )}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
