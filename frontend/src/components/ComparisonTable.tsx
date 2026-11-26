"use client";

import { Fragment } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { isLatinInCyrillic, resolveComparisonDiff } from "@/lib/diff";
import { FIELD_LABELS, formatDateRu, formatKzt } from "@/lib/format";
import type { ComparisonField, ComparisonRow } from "@/lib/types";
import { cn } from "cn";

interface ComparisonTableProps {
  comparison: ComparisonRow[];
  trusted?: boolean;
  className?: string;
}

const MONOSPACE_FIELDS = new Set<ComparisonField>(["iik", "bin", "bik"]);

function formatCellValue(field: ComparisonField, value: string): string {
  if (field === "amount") {
    const cleaned = value.replace(/\s+/g, "").replace(",", ".");
    if (/^-?\d+(\.\d+)?$/.test(cleaned)) {
      return formatKzt(Number(cleaned));
    }
  }
  return value;
}

function HighlightedDiffChars({
  value,
  diffPositions,
  variant,
  monospace,
}: {
  value: string;
  diffPositions: number[];
  variant: "invoice" | "history";
  monospace: boolean;
}) {
  const diffSet = new Set(diffPositions);
  const chars = Array.from(value);

  return (
    <span
      className={cn(
        monospace
          ? "font-mono text-sm tracking-normal lg:tracking-wide break-all [overflow-wrap:anywhere]"
          : "text-sm sm:text-[15px] leading-relaxed break-words [overflow-wrap:anywhere]"
      )}
    >
      {chars.map((char, idx) => {
        const isDiff = diffSet.has(idx);
        const allowBreak = monospace && idx < chars.length - 1;

        if (!isDiff) {
          return (
            <Fragment key={idx}>
              <span>{char}</span>
              {allowBreak && <wbr />}
            </Fragment>
          );
        }

        const isLatinHomoglyph = isLatinInCyrillic(char, value);
        return (
          <Fragment key={idx}>
            <mark
              title={
                isLatinHomoglyph
                  ? "Латинская буква внутри кириллического названия"
                  : undefined
              }
              className={cn(
                "inline-flex items-baseline gap-0.5 rounded-[3px] px-[2px] py-[1px] mx-[0.5px] font-bold sm:px-[3px]",
                variant === "invoice"
                  ? "bg-red-600 text-white shadow-xs"
                  : "bg-emerald-100 text-emerald-950 ring-1 ring-emerald-400"
              )}
            >
              <span
                className={cn(
                  variant === "invoice" &&
                    "underline decoration-white decoration-2 underline-offset-2"
                )}
              >
                {char}
              </span>
              {isLatinHomoglyph && (
                <span
                  title="Латинская буква внутри кириллического названия"
                  className={cn(
                    "ml-0.5 inline-block -translate-y-0.5 rounded px-1 py-[1px] text-[10px] font-semibold leading-none tracking-normal",
                    variant === "invoice"
                      ? "bg-amber-300 text-red-950"
                      : "bg-amber-200 text-amber-950"
                  )}
                >
                  лат.
                </span>
              )}
            </mark>
            {allowBreak && <wbr />}
          </Fragment>
        );
      })}
    </span>
  );
}

export function ComparisonTable({
  comparison,
  trusted = false,
  className,
}: ComparisonTableProps) {
  const preparedRows = comparison.map((row) => {
    const showDiff = !trusted && row.differs;
    const resolvedDiff = trusted
      ? { invoicePositions: [], historyPositions: [] }
      : resolveComparisonDiff(row);
    const hasInvoiceDiff = resolvedDiff.invoicePositions.length > 0;
    const hasHistoryDiff = resolvedDiff.historyPositions.length > 0;
    const isMonospace = MONOSPACE_FIELDS.has(row.field);

    const formattedInvoice = formatCellValue(row.field, row.in_invoice);
    const formattedHistory = row.in_history
      ? formatCellValue(row.field, row.in_history)
      : null;

    return {
      row,
      showDiff,
      resolvedDiff,
      hasInvoiceDiff,
      hasHistoryDiff,
      isMonospace,
      formattedInvoice,
      formattedHistory,
    };
  });

  return (
    <Card className={cn("min-w-0 border-border shadow-xs", className)}>
      <CardHeader className="border-b border-border pb-3.5">
        <CardTitle className="text-base font-semibold">
          Сверка реквизитов со счётом и историей
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        {preparedRows.length === 0 ? (
          <div className="px-4 py-8 text-sm text-muted-foreground sm:px-5">
            Данные для сравнения отсутствуют.
          </div>
        ) : (
          <>
            <div className="divide-y divide-border md:hidden">
              {preparedRows.map(
                ({
                  row,
                  showDiff,
                  resolvedDiff,
                  hasInvoiceDiff,
                  hasHistoryDiff,
                  isMonospace,
                  formattedInvoice,
                  formattedHistory,
                }) => (
                  <div
                    key={row.field}
                    className={cn(
                      "min-w-0 px-4 py-3.5 space-y-2.5",
                      showDiff &&
                        "bg-red-50/70 border-l-4 border-l-red-500 pl-3"
                    )}
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-semibold text-foreground">
                        {FIELD_LABELS[row.field] ?? row.field}
                      </span>
                      {showDiff && (
                        <span className="inline-flex items-center rounded bg-red-100 px-1.5 py-0.5 text-[11px] font-semibold text-red-800">
                          Отличается
                        </span>
                      )}
                    </div>

                    <div className="min-w-0 space-y-0.5">
                      <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                        В счёте
                      </div>
                      <div className="min-w-0">
                        {hasInvoiceDiff ? (
                          <HighlightedDiffChars
                            value={row.in_invoice}
                            diffPositions={resolvedDiff.invoicePositions}
                            variant="invoice"
                            monospace={isMonospace}
                          />
                        ) : (
                          <span
                            className={cn(
                              isMonospace
                                ? "font-mono text-sm tracking-normal break-all [overflow-wrap:anywhere]"
                                : "text-sm break-words [overflow-wrap:anywhere]",
                              showDiff
                                ? "font-semibold text-red-900"
                                : "text-foreground"
                            )}
                          >
                            {formattedInvoice}
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="min-w-0 space-y-0.5">
                      <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                        В истории
                      </div>
                      {formattedHistory ? (
                        <div className="min-w-0 space-y-1">
                          <div className="min-w-0">
                            {hasHistoryDiff ? (
                              <HighlightedDiffChars
                                value={row.in_history ?? ""}
                                diffPositions={resolvedDiff.historyPositions}
                                variant="history"
                                monospace={isMonospace}
                              />
                            ) : (
                              <span
                                className={cn(
                                  isMonospace
                                    ? "font-mono text-sm tracking-normal break-all [overflow-wrap:anywhere]"
                                    : "text-sm break-words [overflow-wrap:anywhere]",
                                  "text-foreground"
                                )}
                              >
                                {formattedHistory}
                              </span>
                            )}
                          </div>
                          {row.last_seen && (
                            <div className="text-xs text-muted-foreground">
                              Последний платёж: {formatDateRu(row.last_seen)}
                            </div>
                          )}
                        </div>
                      ) : (
                        <span className="text-sm text-muted-foreground">
                          Нет в истории
                        </span>
                      )}
                    </div>
                  </div>
                )
              )}
            </div>

            <div className="hidden md:block">
              <Table className="w-full table-fixed">
                <TableHeader>
                  <TableRow className="bg-muted/40 hover:bg-muted/40">
                    <TableHead className="w-[26%] lg:w-[24%] pl-4 lg:pl-5 whitespace-normal">
                      Поле
                    </TableHead>
                    <TableHead className="w-[37%] lg:w-[38%] whitespace-normal">
                      В счёте
                    </TableHead>
                    <TableHead className="w-[37%] lg:w-[38%] pr-4 lg:pr-5 whitespace-normal">
                      В истории (последний платёж, дата)
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {preparedRows.map(
                    ({
                      row,
                      showDiff,
                      resolvedDiff,
                      hasInvoiceDiff,
                      hasHistoryDiff,
                      isMonospace,
                      formattedInvoice,
                      formattedHistory,
                    }) => (
                      <TableRow
                        key={row.field}
                        className={cn(
                          showDiff &&
                            "bg-red-50/70 hover:bg-red-50/90 border-l-4 border-l-red-500"
                        )}
                      >
                        <TableCell className="min-w-0 pl-4 lg:pl-5 py-3.5 align-top font-medium text-foreground whitespace-normal break-words">
                          <div className="flex flex-wrap items-center gap-2">
                            <span>{FIELD_LABELS[row.field] ?? row.field}</span>
                            {showDiff && (
                              <span className="inline-flex items-center rounded bg-red-100 px-1.5 py-0.5 text-[11px] font-semibold text-red-800">
                                Отличается
                              </span>
                            )}
                          </div>
                        </TableCell>

                        <TableCell className="min-w-0 py-3.5 align-top whitespace-normal break-words">
                          {hasInvoiceDiff ? (
                            <HighlightedDiffChars
                              value={row.in_invoice}
                              diffPositions={resolvedDiff.invoicePositions}
                              variant="invoice"
                              monospace={isMonospace}
                            />
                          ) : (
                            <span
                              className={cn(
                                isMonospace
                                  ? "font-mono text-sm tracking-normal lg:tracking-wide break-all [overflow-wrap:anywhere]"
                                  : "text-sm break-words [overflow-wrap:anywhere]",
                                showDiff
                                  ? "font-semibold text-red-900"
                                  : "text-foreground"
                              )}
                            >
                              {formattedInvoice}
                            </span>
                          )}
                        </TableCell>

                        <TableCell className="min-w-0 pr-4 lg:pr-5 py-3.5 align-top whitespace-normal break-words">
                          {formattedHistory ? (
                            <div className="min-w-0 space-y-1">
                              <div className="min-w-0">
                                {hasHistoryDiff ? (
                                  <HighlightedDiffChars
                                    value={row.in_history ?? ""}
                                    diffPositions={
                                      resolvedDiff.historyPositions
                                    }
                                    variant="history"
                                    monospace={isMonospace}
                                  />
                                ) : (
                                  <span
                                    className={cn(
                                      isMonospace
                                        ? "font-mono text-sm tracking-normal lg:tracking-wide break-all [overflow-wrap:anywhere]"
                                        : "text-sm break-words [overflow-wrap:anywhere]",
                                      "text-foreground"
                                    )}
                                  >
                                    {formattedHistory}
                                  </span>
                                )}
                              </div>
                              {row.last_seen && (
                                <div className="text-xs text-muted-foreground">
                                  Последний платёж:{" "}
                                  {formatDateRu(row.last_seen)}
                                </div>
                              )}
                            </div>
                          ) : (
                            <span className="text-sm text-muted-foreground">
                              Нет в истории
                            </span>
                          )}
                        </TableCell>
                      </TableRow>
                    )
                  )}
                </TableBody>
              </Table>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
