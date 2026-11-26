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
          ? "font-mono text-sm tabular-nums break-all [overflow-wrap:anywhere]"
          : "text-sm leading-relaxed break-words [overflow-wrap:anywhere]"
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
              className={
                variant === "invoice" ? "ui-mark-danger" : "ui-mark-ok"
              }
            >
              <span>{char}</span>
              {isLatinHomoglyph && (
                <span title={latinTooltip} className="ui-mark-tag">
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
      <CardHeader className="border-b border-border pb-3">
        <CardTitle>{t.comparison.title}</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        {preparedRows.length === 0 ? (
          <div className="ui-empty">
            <p className="ui-empty-desc">{t.comparison.empty}</p>
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
                      "min-w-0 px-4 py-3 space-y-2",
                      isInvalidField
                        ? "ui-diff-row-invalid pl-3.5"
                        : showDiff && "ui-diff-row-danger pl-3.5"
                    )}
                  >
                    <div className="flex flex-wrap items-baseline gap-2">
                      <span className="text-sm font-medium text-foreground">
                        {t.fields[row.field] ?? row.field}
                      </span>
                      {isInvalidField ? (
                        <span className="text-xs font-medium text-[var(--status-invalid-text)]">
                          {t.comparison.invalidBadge}
                        </span>
                      ) : (
                        showDiff && (
                          <span className="text-xs font-medium text-[var(--status-danger-text)]">
                            {t.comparison.differsBadge}
                          </span>
                        )
                      )}
                    </div>

                    <div className="min-w-0 space-y-0.5">
                      <div className="ui-label-meta">
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
                                ? "font-mono text-sm tabular-nums break-all [overflow-wrap:anywhere]"
                                : isAmount
                                  ? "text-sm font-medium tabular-nums whitespace-nowrap"
                                  : "text-sm break-words [overflow-wrap:anywhere]",
                              isInvalidField
                                ? "font-medium text-[var(--status-invalid-text)]"
                                : showDiff
                                  ? "font-medium text-[var(--status-danger-text)]"
                                  : "text-foreground"
                            )}
                          >
                            {formattedInvoice}
                          </span>
                        )}
                      </div>
                      {isInvalidField && invalidReasons.length > 0 && (
                        <div className="pt-0.5 text-xs font-medium text-[var(--status-invalid-text)] break-words">
                          {invalidReasons.join(" ")}
                        </div>
                      )}
                    </div>

                    <div className="min-w-0 space-y-0.5">
                      <div className="ui-label-meta">
                        {t.comparison.colInHistory}
                      </div>
                      {formattedHistory ? (
                        <div className="min-w-0 space-y-0.5">
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
                                    ? "font-mono text-sm tabular-nums break-all [overflow-wrap:anywhere]"
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
                            <div className="text-xs text-muted-foreground tabular-nums">
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
                  <TableRow className="hover:bg-transparent">
                    <TableHead className="w-[26%] lg:w-[24%] pl-4 whitespace-normal">
                      {t.comparison.colField}
                    </TableHead>
                    <TableHead className="w-[37%] lg:w-[38%] whitespace-normal">
                      {t.comparison.colInInvoice}
                    </TableHead>
                    <TableHead className="w-[37%] lg:w-[38%] pr-4 whitespace-normal">
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
                            ? "ui-diff-row-invalid"
                            : showDiff && "ui-diff-row-danger"
                        )}
                      >
                        <TableCell className="min-w-0 pl-4 align-top font-medium text-foreground whitespace-normal break-words">
                          <div className="flex flex-wrap items-baseline gap-2">
                            <span>{t.fields[row.field] ?? row.field}</span>
                            {isInvalidField ? (
                              <span className="text-xs font-medium text-[var(--status-invalid-text)]">
                                {t.comparison.invalidBadge}
                              </span>
                            ) : (
                              showDiff && (
                                <span className="text-xs font-medium text-[var(--status-danger-text)]">
                                  {t.comparison.differsBadge}
                                </span>
                              )
                            )}
                          </div>
                        </TableCell>

                        <TableCell className="min-w-0 align-top whitespace-normal break-words">
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
                                    ? "font-mono text-sm tabular-nums break-all [overflow-wrap:anywhere]"
                                    : isAmount
                                      ? "text-sm font-medium tabular-nums whitespace-nowrap"
                                      : "text-sm break-words [overflow-wrap:anywhere]",
                                  isInvalidField
                                    ? "font-medium text-[var(--status-invalid-text)]"
                                    : showDiff
                                      ? "font-medium text-[var(--status-danger-text)]"
                                      : "text-foreground"
                                )}
                              >
                                {formattedInvoice}
                              </span>
                            )}
                            {isInvalidField && invalidReasons.length > 0 && (
                              <div className="text-xs font-medium text-[var(--status-invalid-text)] break-words">
                                {invalidReasons.join(" ")}
                              </div>
                            )}
                          </div>
                        </TableCell>

                        <TableCell className="min-w-0 pr-4 align-top whitespace-normal break-words">
                          {formattedHistory ? (
                            <div className="min-w-0 space-y-0.5">
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
                                        ? "font-mono text-sm tabular-nums break-all [overflow-wrap:anywhere]"
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
                                <div className="text-xs text-muted-foreground tabular-nums">
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
