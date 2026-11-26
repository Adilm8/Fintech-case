"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChevronRight, Copy, Lock } from "lucide-react";
import { StatusBadge } from "@/components/prod/StatusBadge";
import { SupplierBadge } from "@/components/prod/SupplierBadge";
import { VerdictBadge } from "@/components/VerdictBadge";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useT } from "@/i18n";
import type { Payment } from "@/lib/prod/types";

interface PaymentsTableProps {
  payments: Payment[];
}

export function PaymentsTable({ payments }: PaymentsTableProps) {
  const router = useRouter();
  const { t, formatMoney, formatDate, interpolate } = useT();

  return (
    <>
      {/* Mobile cards (< md) */}
      <div className="flex flex-col gap-3 p-3 sm:p-4 md:hidden">
        {payments.map((payment) => {
          const isBudget =
            payment.check.verdict === "green" &&
            payment.check.signals.some((s) => s.rule_id === "budget_payment");
          const hasPendingAccount =
            payment.supplier.known && !payment.supplier.account_known;

          return (
            <Link
              key={payment.id}
              href={`/payments/${payment.id}`}
              className="block w-full min-h-11 rounded-xl border border-border bg-card p-3.5 text-left shadow-xs transition-all hover:bg-muted/50 active:bg-muted/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1"
            >
              <div className="flex items-start justify-between gap-2.5">
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="text-base font-semibold leading-snug text-foreground break-words">
                    {payment.request.recipient_name}
                  </div>
                  {(payment.doc_number || payment.doc_date) && (
                    <div className="text-xs text-muted-foreground">
                      {payment.doc_number
                        ? interpolate(t.prod.payments.docNumberPrefix, {
                            num: payment.doc_number,
                          })
                        : ""}
                      {payment.doc_number && payment.doc_date ? " · " : ""}
                      {payment.doc_date ? formatDate(payment.doc_date) : ""}
                    </div>
                  )}
                </div>
                <VerdictBadge
                  verdict={payment.check.verdict}
                  label={isBudget ? t.signalRules.budget_payment : undefined}
                  className="shrink-0"
                />
              </div>

              <div className="mt-2 flex items-center justify-between gap-2">
                <div className="text-xl font-bold tabular-nums whitespace-nowrap text-foreground">
                  {formatMoney(payment.request.amount_kzt)}
                </div>
                <div className="flex items-center gap-1.5">
                  <StatusBadge status={payment.status} />
                  <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
                </div>
              </div>

              <div className="mt-1.5 flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5 font-mono text-xs text-muted-foreground">
                <span>
                  {interpolate(t.common.binPrefix, {
                    bin: payment.request.recipient_bin,
                  })}
                </span>
                <span aria-hidden="true">·</span>
                <span className="break-all">{payment.request.recipient_iik}</span>
              </div>

              <p className="mt-2 line-clamp-2 text-sm text-muted-foreground break-words">
                {payment.request.purpose}
              </p>

              <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                <SupplierBadge
                  requisitesChangedDaysAgo={
                    payment.supplier.requisites_changed_days_ago
                  }
                  hasPendingChange={hasPendingAccount}
                  isNewSupplier={!payment.supplier.known}
                />
                {payment.duplicate_of && (
                  <Badge
                    variant="outline"
                    className="h-auto gap-1 border-amber-300 bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-900"
                  >
                    <Copy className="size-3 shrink-0" />
                    <span>{t.prod.payments.possibleDuplicate}</span>
                  </Badge>
                )}
                {payment.permissions.sign_block_code ===
                  "threshold_requires_approval" && (
                  <Badge
                    variant="outline"
                    className="h-auto gap-1 border-amber-300 bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-900"
                  >
                    <Lock className="size-3 shrink-0" />
                    <span>{t.prod.payments.thresholdApprovalBadge}</span>
                  </Badge>
                )}
              </div>
            </Link>
          );
        })}
      </div>

      {/* Desktop table (>= md) */}
      <div className="hidden md:block overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/40 hover:bg-muted/40">
              <TableHead className="w-[175px] pl-4 lg:pl-5">
                {t.queue.colCheckResult}
              </TableHead>
              <TableHead>{t.queue.colRecipient}</TableHead>
              <TableHead className="w-[155px] text-right">
                {t.queue.colAmount}
              </TableHead>
              <TableHead className="w-[130px]">{t.prod.payments.colDoc}</TableHead>
              <TableHead className="w-[140px]">
                {t.prod.payments.colStatus}
              </TableHead>
              <TableHead className="w-9 pr-3 lg:pr-4" />
            </TableRow>
          </TableHeader>

          <TableBody>
            {payments.map((payment) => {
              const isBudget =
                payment.check.verdict === "green" &&
                payment.check.signals.some((s) => s.rule_id === "budget_payment");
              const hasPendingAccount =
                payment.supplier.known && !payment.supplier.account_known;

              return (
                <TableRow
                  key={payment.id}
                  tabIndex={0}
                  role="link"
                  onClick={() => router.push(`/payments/${payment.id}`)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      router.push(`/payments/${payment.id}`);
                    }
                  }}
                  className="cursor-pointer transition-colors hover:bg-muted/45 focus-visible:bg-accent/50 focus-visible:outline-none"
                >
                  <TableCell className="pl-4 lg:pl-5 py-3.5 align-top">
                    <VerdictBadge
                      verdict={payment.check.verdict}
                      label={isBudget ? t.signalRules.budget_payment : undefined}
                    />
                  </TableCell>

                  <TableCell className="min-w-0 max-w-[380px] py-3.5 align-top whitespace-normal">
                    <div className="space-y-1">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="font-semibold text-foreground break-words">
                          {payment.request.recipient_name}
                        </span>
                        {payment.duplicate_of && (
                          <Badge
                            variant="outline"
                            className="h-auto gap-1 border-amber-300 bg-amber-50 px-1.5 py-0.5 text-[11px] font-medium text-amber-900"
                          >
                            <Copy className="size-3 shrink-0" />
                            <span>{t.prod.payments.possibleDuplicate}</span>
                          </Badge>
                        )}
                        {payment.permissions.sign_block_code ===
                          "threshold_requires_approval" && (
                          <Badge
                            variant="outline"
                            className="h-auto gap-1 border-amber-300 bg-amber-50 px-1.5 py-0.5 text-[11px] font-medium text-amber-900"
                          >
                            <Lock className="size-3 shrink-0" />
                            <span>{t.prod.payments.thresholdApprovalBadge}</span>
                          </Badge>
                        )}
                      </div>
                      <div className="flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5 font-mono text-xs text-muted-foreground">
                        <span>
                          {interpolate(t.common.binPrefix, {
                            bin: payment.request.recipient_bin,
                          })}
                        </span>
                        <span aria-hidden="true">·</span>
                        <span className="break-all">
                          {payment.request.recipient_iik}
                        </span>
                      </div>
                      {payment.request.purpose && (
                        <p className="line-clamp-1 text-xs text-muted-foreground break-words">
                          {payment.request.purpose}
                        </p>
                      )}
                      <SupplierBadge
                        requisitesChangedDaysAgo={
                          payment.supplier.requisites_changed_days_ago
                        }
                        hasPendingChange={hasPendingAccount}
                        isNewSupplier={!payment.supplier.known}
                        className="pt-0.5"
                      />
                    </div>
                  </TableCell>

                  <TableCell className="py-3.5 align-top text-right font-semibold tabular-nums whitespace-nowrap text-foreground">
                    {formatMoney(payment.request.amount_kzt)}
                  </TableCell>

                  <TableCell className="py-3.5 align-top whitespace-normal">
                    <div className="space-y-0.5 text-xs">
                      <div className="font-medium text-foreground">
                        {payment.doc_number
                          ? interpolate(t.prod.payments.docNumberPrefix, {
                              num: payment.doc_number,
                            })
                          : "—"}
                      </div>
                      <div className="text-muted-foreground">
                        {payment.doc_date
                          ? formatDate(payment.doc_date)
                          : formatDate(payment.created_at)}
                      </div>
                      {payment.source !== "manual" && (
                        <Badge
                          variant="secondary"
                          className="h-auto px-1.5 py-0 text-[10px] font-medium"
                        >
                          {t.prod.sources[payment.source]}
                        </Badge>
                      )}
                    </div>
                  </TableCell>

                  <TableCell className="py-3.5 align-top">
                    <StatusBadge status={payment.status} />
                  </TableCell>

                  <TableCell className="pr-3 lg:pr-4 py-3.5 align-middle text-right">
                    <ChevronRight className="ml-auto size-4 text-muted-foreground" />
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
    </>
  );
}
