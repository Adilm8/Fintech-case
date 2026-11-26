"use client";

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
          ? "font-mono text-sm tracking-wider sm:text-[15px] break-all"
          : "text-sm sm:text-[15px] leading-relaxed break-words"
      )}
    >
      {chars.map((char, idx) => {
        const isDiff = diffSet.has(idx);
        if (!isDiff) {
          return <span key={idx}>{char}</span>;
        }

        const isLatinHomoglyph = isLatinInCyrillic(char, value);
        return (
          <mark
            key={idx}
            title={
              isLatinHomoglyph
                ? "Латинская буква внутри кириллического названия"
                : undefined
            }
            className={cn(
              "inline-flex items-baseline gap-0.5 rounded-[3px] px-[3px] py-[1px] mx-[0.5px] font-bold",
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
  return (
    <Card className={cn("border-border shadow-xs", className)}>
      <CardHeader className="border-b border-border pb-3.5">
        <CardTitle className="text-base font-semibold">
          Сверка реквизитов со счётом и историей
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        {comparison.length === 0 ? (
          <div className="px-5 py-8 text-sm text-muted-foreground">
            Данные для сравнения отсутствуют.
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40 hover:bg-muted/40">
                <TableHead className="w-[220px] pl-5">Поле</TableHead>
                <TableHead>В счёте</TableHead>
                <TableHead className="pr-5">
                  В истории (последний платёж, дата)
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {comparison.map((row) => {
                const showDiff = !trusted && row.differs;
                const resolvedDiff = trusted
                  ? { invoicePositions: [], historyPositions: [] }
                  : resolveComparisonDiff(row);
                const hasInvoiceDiff =
                  resolvedDiff.invoicePositions.length > 0;
                const hasHistoryDiff =
                  resolvedDiff.historyPositions.length > 0;
                const isMonospace = MONOSPACE_FIELDS.has(row.field);

                const formattedInvoice = formatCellValue(
                  row.field,
                  row.in_invoice
                );
                const formattedHistory = row.in_history
                  ? formatCellValue(row.field, row.in_history)
                  : null;

                return (
                  <TableRow
                    key={row.field}
                    className={cn(
                      showDiff &&
                        "bg-red-50/70 hover:bg-red-50/90 border-l-4 border-l-red-500"
                    )}
                  >
                    <TableCell className="pl-5 py-3.5 font-medium text-foreground whitespace-normal">
                      <div className="flex flex-wrap items-center gap-2">
                        <span>{FIELD_LABELS[row.field] ?? row.field}</span>
                        {showDiff && (
                          <span className="inline-flex items-center rounded bg-red-100 px-1.5 py-0.5 text-[11px] font-semibold text-red-800">
                            Отличается
                          </span>
                        )}
                      </div>
                    </TableCell>

                    <TableCell className="py-3.5 whitespace-normal">
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
                              ? "font-mono text-sm tracking-wider"
                              : "text-sm",
                            showDiff
                              ? "font-semibold text-red-900"
                              : "text-foreground"
                          )}
                        >
                          {formattedInvoice}
                        </span>
                      )}
                    </TableCell>

                    <TableCell className="pr-5 py-3.5 whitespace-normal">
                      {formattedHistory ? (
                        <div className="space-y-1">
                          <div>
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
                                    ? "font-mono text-sm tracking-wider"
                                    : "text-sm",
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
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
