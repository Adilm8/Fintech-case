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
import { useT } from "@/i18n";
import { isLatinInCyrillic, resolveComparisonDiff } from "@/lib/diff";
import { localizeBackendText, parseKztString } from "@/lib/format";
import type { ComparisonField, ComparisonRow } from "@/lib/types";
import { cn } from "cn";

interface ComparisonTableProps {
  comparison: ComparisonRow[];
  trusted?: boolean;
  invalidFields?: Partial<Record<ComparisonField, string[]>>;
  className?: string;
}

const MONOSPACE_FIELDS = new Set<ComparisonField>(["iik", "bin", "bik"]);
const TRUST_NEUTRALIZED_FIELDS = new Set<ComparisonField>([
  "iik",
  "bik",
  "bank",
]);

function HighlightedDiffChars({
  value,
  diffPositions,
  variant,
  monospace,
  latinTag,
  latinTooltip,
}: {
  value: string;
  diffPositions: number[];
  variant: "invoice" | "history";
  monospace: boolean;
  latinTag: string;
  latinTooltip: string;
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
              title={isLatinHomoglyph ? latinTooltip : undefined}
              className={cn(
                "inline-flex items-baseline gap-0.5 rounded-[3px] px-[2px] py-[1px] mx-[0.5px] font-bold sm:px-[3px]",
                variant === "invoice"
                  ? "bg-red-600 text-white shadow-xs"
                  : "bg-[#E8F8F2] text-[#064A34] ring-1 ring-[#00AB75]/50"
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
                  title={latinTooltip}
                  className={cn(
                    "ml-0.5 inline-block -translate-y-0.5 rounded px-1 py-[1px] text-[10px] font-semibold leading-none tracking-normal",
                    variant === "invoice"
                      ? "bg-amber-300 text-red-950"
                      : "bg-amber-200 text-amber-950"
                  )}
                >
                  {latinTag}
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
  invalidFields,
  className,
}: ComparisonTableProps) {
  const { t, lang, formatMoney, formatDate, interpolate } = useT();

  const formatCellValue = (field: ComparisonField, value: string): string => {
    if (field === "amount") {
      const parsed = parseKztString(value);
      if (parsed !== null) {
        return formatMoney(parsed);
      }
    }
    return value;
  };

  const preparedRows = comparison.map((row) => {
    const fieldInvalidReasons = invalidFields?.[row.field];
    const isInvalidField = Boolean(fieldInvalidReasons);
    const isNeutralizedByTrust =
      trusted && TRUST_NEUTRALIZED_FIELDS.has(row.field) && !isInvalidField;
    const showDiff = !isNeutralizedByTrust && row.differs;
    const resolvedDiff = isNeutralizedByTrust
      ? { invoicePositions: [], historyPositions: [] }
      : resolveComparisonDiff(row);
    const hasInvoiceDiff = resolvedDiff.invoicePositions.length > 0;
    const hasHistoryDiff = resolvedDiff.historyPositions.length > 0;
    const isMonospace = MONOSPACE_FIELDS.has(row.field);
    const isAmount = row.field === "amount";

    const formattedInvoice = formatCellValue(row.field, row.in_invoice);
    const formattedHistory = row.in_history
      ? formatCellValue(row.field, row.in_history)
      : null;

    return {
      row,
      isInvalidField,
      invalidReasons: (fieldInvalidReasons ?? []).map((msg) =>
        localizeBackendText(msg, lang)
      ),
      showDiff,
      resolvedDiff,
      hasInvoiceDiff,
      hasHistoryDiff,
      isMonospace,
      isAmount,
      formattedInvoice,
      formattedHistory,
    };
  });

  return (
    <Card className={cn("min-w-0", className)}>
      <CardHeader className="border-b border-border pb-3.5">
        <CardTitle className="text-base font-semibold">
          {t.comparison.title}
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        {preparedRows.length === 0 ? (
          <div className="px-4 py-8 text-sm text-muted-foreground sm:px-5">
            {t.comparison.empty}
          </div>
        ) : (
          <>
            <div className="divide-y divide-border md:hidden">
              {preparedRows.map(
                ({
                  row,
                  isInvalidField,
                  invalidReasons,
                  showDiff,
                  resolvedDiff,
                  hasInvoiceDiff,
                  hasHistoryDiff,
                  isMonospace,
                  isAmount,
                  formattedInvoice,
                  formattedHistory,
                }) => (
                  <div
                    key={row.field}
                    className={cn(
                      "min-w-0 px-4 py-3.5 space-y-2.5",
                      isInvalidField
                        ? "bg-rose-50/85 border-l-4 border-l-rose-700 pl-3"
                        : showDiff &&
                            "bg-red-50/70 border-l-4 border-l-red-500 pl-3"
                    )}
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-semibold text-foreground">
                        {t.fields[row.field] ?? row.field}
                      </span>
                      {isInvalidField ? (
                        <span className="inline-flex items-center rounded bg-rose-200/80 px-1.5 py-0.5 text-[11px] font-semibold text-rose-950">
                          {t.comparison.invalidBadge}
                        </span>
                      ) : (
                        showDiff && (
                          <span className="inline-flex items-center rounded bg-red-100 px-1.5 py-0.5 text-[11px] font-semibold text-red-800">
                            {t.comparison.differsBadge}
                          </span>
                        )
                      )}
                    </div>

                    <div className="min-w-0 space-y-0.5">
                      <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                        {t.comparison.colInInvoice}
                      </div>
                      <div className="min-w-0">
                        {hasInvoiceDiff ? (
                          <HighlightedDiffChars
                            value={row.in_invoice}
                            diffPositions={resolvedDiff.invoicePositions}
                            variant="invoice"
                            monospace={isMonospace}
                            latinTag={t.comparison.latinTag}
                            latinTooltip={t.comparison.latinTooltip}
                          />
                        ) : (
                          <span
                            className={cn(
                              isMonospace
                                ? "font-mono text-sm tracking-normal break-all [overflow-wrap:anywhere]"
                                : isAmount
                                  ? "text-sm font-medium tabular-nums whitespace-nowrap"
                                  : "text-sm break-words [overflow-wrap:anywhere]",
                              isInvalidField
                                ? "font-semibold text-rose-950"
                                : showDiff
                                  ? "font-semibold text-red-900"
                                  : "text-foreground"
                            )}
                          >
                            {formattedInvoice}
                          </span>
                        )}
                      </div>
                      {isInvalidField && invalidReasons.length > 0 && (
                        <div className="pt-1 text-xs font-medium text-rose-900 break-words">
                          {invalidReasons.join(" ")}
                        </div>
                      )}
                    </div>

                    <div className="min-w-0 space-y-0.5">
                      <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                        {t.comparison.colInHistory}
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
                                latinTag={t.comparison.latinTag}
                                latinTooltip={t.comparison.latinTooltip}
                              />
                            ) : (
                              <span
                                className={cn(
                                  isMonospace
                                    ? "font-mono text-sm tracking-normal break-all [overflow-wrap:anywhere]"
                                    : isAmount
                                      ? "text-sm tabular-nums whitespace-nowrap"
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
                              {interpolate(t.comparison.lastPayment, {
                                date: formatDate(row.last_seen),
                              })}
                            </div>
                          )}
                        </div>
                      ) : (
                        <span className="text-sm text-muted-foreground">
                          {t.comparison.notInHistory}
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
                      {t.comparison.colField}
                    </TableHead>
                    <TableHead className="w-[37%] lg:w-[38%] whitespace-normal">
                      {t.comparison.colInInvoice}
                    </TableHead>
                    <TableHead className="w-[37%] lg:w-[38%] pr-4 lg:pr-5 whitespace-normal">
                      {t.comparison.colInHistoryFull}
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {preparedRows.map(
                    ({
                      row,
                      isInvalidField,
                      invalidReasons,
                      showDiff,
                      resolvedDiff,
                      hasInvoiceDiff,
                      hasHistoryDiff,
                      isMonospace,
                      isAmount,
                      formattedInvoice,
                      formattedHistory,
                    }) => (
                      <TableRow
                        key={row.field}
                        className={cn(
                          isInvalidField
                            ? "bg-rose-50/85 hover:bg-rose-50 border-l-4 border-l-rose-700"
                            : showDiff &&
                                "bg-red-50/70 hover:bg-red-50/90 border-l-4 border-l-red-500"
                        )}
                      >
                        <TableCell className="min-w-0 pl-4 lg:pl-5 py-3.5 align-top font-medium text-foreground whitespace-normal break-words">
                          <div className="flex flex-wrap items-center gap-2">
                            <span>{t.fields[row.field] ?? row.field}</span>
                            {isInvalidField ? (
                              <span className="inline-flex items-center rounded bg-rose-200/80 px-1.5 py-0.5 text-[11px] font-semibold text-rose-950">
                                {t.comparison.invalidBadge}
                              </span>
                            ) : (
                              showDiff && (
                                <span className="inline-flex items-center rounded bg-red-100 px-1.5 py-0.5 text-[11px] font-semibold text-red-800">
                                  {t.comparison.differsBadge}
                                </span>
                              )
                            )}
                          </div>
                        </TableCell>

                        <TableCell className="min-w-0 py-3.5 align-top whitespace-normal break-words">
                          <div className="min-w-0 space-y-1">
                            {hasInvoiceDiff ? (
                              <HighlightedDiffChars
                                value={row.in_invoice}
                                diffPositions={resolvedDiff.invoicePositions}
                                variant="invoice"
                                monospace={isMonospace}
                                latinTag={t.comparison.latinTag}
                                latinTooltip={t.comparison.latinTooltip}
                              />
                            ) : (
                              <span
                                className={cn(
                                  isMonospace
                                    ? "font-mono text-sm tracking-normal lg:tracking-wide break-all [overflow-wrap:anywhere]"
                                    : isAmount
                                      ? "text-sm font-medium tabular-nums whitespace-nowrap"
                                      : "text-sm break-words [overflow-wrap:anywhere]",
                                  isInvalidField
                                    ? "font-semibold text-rose-950"
                                    : showDiff
                                      ? "font-semibold text-red-900"
                                      : "text-foreground"
                                )}
                              >
                                {formattedInvoice}
                              </span>
                            )}
                            {isInvalidField && invalidReasons.length > 0 && (
                              <div className="text-xs font-medium text-rose-900 break-words">
                                {invalidReasons.join(" ")}
                              </div>
                            )}
                          </div>
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
                                    latinTag={t.comparison.latinTag}
                                    latinTooltip={t.comparison.latinTooltip}
                                  />
                                ) : (
                                  <span
                                    className={cn(
                                      isMonospace
                                        ? "font-mono text-sm tracking-normal lg:tracking-wide break-all [overflow-wrap:anywhere]"
                                        : isAmount
                                          ? "text-sm tabular-nums whitespace-nowrap"
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
                                  {interpolate(t.comparison.lastPayment, {
                                    date: formatDate(row.last_seen),
                                  })}
                                </div>
                              )}
                            </div>
                          ) : (
                            <span className="text-sm text-muted-foreground">
                              {t.comparison.notInHistory}
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
