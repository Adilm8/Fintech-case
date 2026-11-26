"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChevronRight } from "lucide-react";
import { StatusBadge } from "@/components/prod/StatusBadge";
import { SupplierBadge } from "@/components/prod/SupplierBadge";
import { VerdictBadge } from "@/components/VerdictBadge";
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
      {/* Mobile flat list (< md) */}
      <div className="divide-y divide-border md:hidden">
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
              className="block w-full min-h-11 bg-card px-4 py-3 text-left transition-colors hover:bg-muted/40 active:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
            >
              <div className="flex items-start justify-between gap-2.5">
                <div className="min-w-0 flex-1 space-y-0.5">
                  <div className="text-sm font-semibold leading-snug text-foreground break-words">
                    {payment.request.recipient_name}
                  </div>
                  {(payment.doc_number || payment.doc_date) && (
                    <div className="text-xs text-muted-foreground tabular-nums">
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
                <div className="text-base font-semibold tabular-nums whitespace-nowrap text-foreground">
                  {formatMoney(payment.request.amount_kzt)}
                </div>
                <div className="flex items-center gap-1.5">
                  <StatusBadge status={payment.status} />
                  <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
                </div>
              </div>

              <div className="mt-1.5 flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5 font-mono text-xs tabular-nums text-muted-foreground">
                <span>
                  {interpolate(t.common.binPrefix, {
                    bin: payment.request.recipient_bin,
                  })}
                </span>
                <span aria-hidden="true">·</span>
                <span className="break-all">{payment.request.recipient_iik}</span>
              </div>

              {payment.request.purpose && (
                <p className="mt-1.5 line-clamp-2 text-xs text-muted-foreground break-words">
                  {payment.request.purpose}
                </p>
              )}

              <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5">
                <SupplierBadge
                  requisitesChangedDaysAgo={
                    payment.supplier.requisites_changed_days_ago
                  }
                  hasPendingChange={hasPendingAccount}
                  isNewSupplier={!payment.supplier.known}
                />
                {payment.duplicate_of && (
                  <span className="ui-tag">
                    {t.prod.payments.possibleDuplicate}
                  </span>
                )}
                {payment.permissions.sign_block_code ===
                  "threshold_requires_approval" && (
                  <span className="ui-tag">
                    {t.prod.payments.thresholdApprovalBadge}
                  </span>
                )}
                {payment.source !== "manual" && (
                  <span className="ui-tag">
                    {t.prod.sources[payment.source]}
                  </span>
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
            <TableRow className="hover:bg-transparent">
              <TableHead className="w-[170px] pl-4">
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
              <TableHead className="w-8 pr-4" />
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
                  className="cursor-pointer focus-visible:bg-muted/60 focus-visible:outline-none"
                >
                  <TableCell className="pl-4 py-2.5 align-top">
                    <VerdictBadge
                      verdict={payment.check.verdict}
                      label={isBudget ? t.signalRules.budget_payment : undefined}
                    />
                  </TableCell>

                  <TableCell className="min-w-0 max-w-[380px] py-2.5 align-top whitespace-normal">
                    <div className="space-y-1">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="font-medium text-foreground break-words">
                          {payment.request.recipient_name}
                        </span>
                        {payment.duplicate_of && (
                          <span className="ui-tag">
                            {t.prod.payments.possibleDuplicate}
                          </span>
                        )}
                        {payment.permissions.sign_block_code ===
                          "threshold_requires_approval" && (
                          <span className="ui-tag">
                            {t.prod.payments.thresholdApprovalBadge}
                          </span>
                        )}
                      </div>
                      <div className="flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5 font-mono text-xs tabular-nums text-muted-foreground">
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

                  <TableCell className="py-2.5 align-top text-right font-medium tabular-nums whitespace-nowrap text-foreground">
                    {formatMoney(payment.request.amount_kzt)}
                  </TableCell>

                  <TableCell className="py-2.5 align-top whitespace-normal">
                    <div className="space-y-0.5 text-xs tabular-nums">
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
                        <span className="ui-tag">
                          {t.prod.sources[payment.source]}
                        </span>
                      )}
                    </div>
                  </TableCell>

                  <TableCell className="py-2.5 align-top">
                    <StatusBadge status={payment.status} />
                  </TableCell>

                  <TableCell className="pr-4 py-2.5 align-middle text-right">
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
