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

const LATIN_TO_CYRILLIC_HOMOGLYPH: Record<string, string> = {
  A: "А",
  B: "В",
  C: "С",
  E: "Е",
  H: "Н",
  I: "І",
  K: "К",
  M: "М",
  O: "О",
  P: "Р",
  T: "Т",
  X: "Х",
  Y: "У",
  a: "а",
  c: "с",
  e: "е",
  i: "і",
  k: "к",
  m: "м",
  o: "о",
  p: "р",
  x: "х",
  y: "у",
};

function countPositionalDiffs(a: string, b: string): number {
  const aChars = Array.from(a);
  const bChars = Array.from(b);
  const maxLen = Math.max(aChars.length, bChars.length);
  let diffs = 0;
  for (let i = 0; i < maxLen; i += 1) {
    if (aChars[i] !== bChars[i]) {
      diffs += 1;
    }
  }
  return diffs;
}

function splitIntoGroupsOfFour(value: string): string[] {
  const compact = value.replace(/\s+/g, "");
  const chars = Array.from(compact || value);
  const groups: string[] = [];
  for (let i = 0; i < chars.length; i += 4) {
    groups.push(chars.slice(i, i + 4).join(""));
  }
  return groups;
}

function GroupedIikValue({ value }: { value: string }) {
  const groups = splitIntoGroupsOfFour(value);
  return (
    <>
      {groups.map((group, groupIdx) => (
        <Fragment key={groupIdx}>
          {groupIdx > 0 && " "}
          <span className="inline-block whitespace-nowrap">{group}</span>
        </Fragment>
      ))}
    </>
  );
}

function collectHomoglyphChars(
  value: string,
  diffPositions: number[]
): { latin: string; cyrillic: string | null }[] {
  const chars = Array.from(value);
  const seen = new Set<string>();
  const result: { latin: string; cyrillic: string | null }[] = [];

  for (const pos of diffPositions) {
    const ch = chars[pos];
    if (!ch || seen.has(ch)) continue;
    if (isLatinInCyrillic(ch, value)) {
      seen.add(ch);
      result.push({
        latin: ch,
        cyrillic: LATIN_TO_CYRILLIC_HOMOGLYPH[ch] ?? null,
      });
    }
  }
  return result;
}

function HighlightedDiffChars({
  value,
  diffPositions,
  variant,
  monospace,
  groupBy4 = false,
  latinTooltip,
}: {
  value: string;
  diffPositions: number[];
  variant: "invoice" | "history";
  monospace: boolean;
  groupBy4?: boolean;
  latinTooltip: string;
}) {
  const diffSet = new Set(diffPositions);
  const chars = Array.from(value);

  if (groupBy4) {
    const groups: { idx: number; char: string }[][] = [];
    for (let i = 0; i < chars.length; i += 4) {
      groups.push(
        chars.slice(i, i + 4).map((char, offset) => ({
          idx: i + offset,
          char,
        }))
      );
    }

    return (
      <span className="font-mono text-sm tabular-nums">
        {groups.map((group, groupIdx) => (
          <Fragment key={groupIdx}>
            {groupIdx > 0 && " "}
            <span className="inline-block whitespace-nowrap">
              {group.map(({ idx, char }) => {
                if (!diffSet.has(idx)) {
                  return <span key={idx}>{char}</span>;
                }
                return (
                  <mark
                    key={idx}
                    className={
                      variant === "invoice" ? "ui-mark-danger" : "ui-mark-ok"
                    }
                  >
                    {char}
                  </mark>
                );
              })}
            </span>
          </Fragment>
        ))}
      </span>
    );
  }

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
              {char}
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
    const isIik = row.field === "iik";
    const iikDiffCount =
      isIik && row.in_history
        ? countPositionalDiffs(row.in_invoice, row.in_history)
        : 0;
    const isFullIikDiff =
      isIik &&
      showDiff &&
      !isInvalidField &&
      Boolean(row.in_history) &&
      (iikDiffCount > 4 || resolvedDiff.invoicePositions.length === 0);
    const hasInvoiceDiff =
      !isFullIikDiff && resolvedDiff.invoicePositions.length > 0;
    const hasHistoryDiff =
      !isFullIikDiff && resolvedDiff.historyPositions.length > 0;
    const isMonospace = MONOSPACE_FIELDS.has(row.field);
    const isAmount = row.field === "amount";

    const homoglyphBadges =
      row.field === "name" && resolvedDiff.invoicePositions.length > 0
        ? collectHomoglyphChars(
            row.in_invoice,
            resolvedDiff.invoicePositions
          ).map(({ latin, cyrillic }) => ({
            key: `${latin}-${cyrillic ?? "generic"}`,
            label: cyrillic
              ? interpolate(t.comparison.homoglyphBadge, { latin, cyrillic })
              : interpolate(t.comparison.homoglyphBadgeGeneric, { latin }),
          }))
        : [];

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
      isIik,
      isFullIikDiff,
      hasInvoiceDiff,
      hasHistoryDiff,
      isMonospace,
      isAmount,
      homoglyphBadges,
      formattedInvoice,
      formattedHistory,
    };
  });

  const renderInvoiceValue = (
    item: (typeof preparedRows)[number]
  ) => {
    const {
      row,
      isInvalidField,
      showDiff,
      resolvedDiff,
      isIik,
      isFullIikDiff,
      hasInvoiceDiff,
      isMonospace,
      isAmount,
      formattedInvoice,
    } = item;

    if (isFullIikDiff) {
      return (
        <mark className="ui-mark-danger inline-block rounded-[4px] px-1.5 py-0.5 font-mono text-sm tabular-nums no-underline">
          <GroupedIikValue value={row.in_invoice} />
        </mark>
      );
    }

    if (hasInvoiceDiff) {
      return (
        <HighlightedDiffChars
          value={row.in_invoice}
          diffPositions={resolvedDiff.invoicePositions}
          variant="invoice"
          monospace={isMonospace}
          groupBy4={isIik}
          latinTooltip={t.comparison.latinTooltip}
        />
      );
    }

    if (isIik) {
      return (
        <span
          className={cn(
            "font-mono text-sm tabular-nums",
            isInvalidField
              ? "font-medium text-[var(--status-invalid-text)]"
              : showDiff
                ? "font-medium text-[var(--status-danger-text)]"
                : "text-foreground"
          )}
        >
          <GroupedIikValue value={row.in_invoice} />
        </span>
      );
    }

    return (
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
    );
  };

  const renderHistoryValue = (
    item: (typeof preparedRows)[number]
  ) => {
    const {
      row,
      resolvedDiff,
      isIik,
      isFullIikDiff,
      hasHistoryDiff,
      isMonospace,
      isAmount,
      formattedHistory,
    } = item;

    if (!formattedHistory || !row.in_history) {
      return null;
    }

    if (isFullIikDiff) {
      return (
        <mark className="ui-mark-ok inline-block rounded-[4px] px-1.5 py-0.5 font-mono text-sm tabular-nums">
          <GroupedIikValue value={row.in_history} />
        </mark>
      );
    }

    if (hasHistoryDiff) {
      return (
        <HighlightedDiffChars
          value={row.in_history}
          diffPositions={resolvedDiff.historyPositions}
          variant="history"
          monospace={isMonospace}
          groupBy4={isIik}
          latinTooltip={t.comparison.latinTooltip}
        />
      );
    }

    if (isIik) {
      return (
        <span className="font-mono text-sm tabular-nums text-foreground">
          <GroupedIikValue value={row.in_history} />
        </span>
      );
    }

    return (
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
    );
  };

  const renderHomoglyphBadges = (
    badges: { key: string; label: string }[]
  ) => {
    if (badges.length === 0) return null;
    return (
      <div className="flex flex-wrap gap-1.5 pt-1">
        {badges.map((badge) => (
          <span
            key={badge.key}
            title={t.comparison.latinTooltip}
            className="inline-flex items-center rounded-full border border-[#F59E0B]/40 bg-[#FEF3C7] px-2 py-0.5 text-xs font-medium text-[#92400E]"
          >
            {badge.label}
          </span>
        ))}
      </div>
    );
  };

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
              {preparedRows.map((item) => {
                const {
                  row,
                  isInvalidField,
                  invalidReasons,
                  showDiff,
                  homoglyphBadges,
                  formattedHistory,
                } = item;

                return (
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
                      <div className="min-w-0">{renderInvoiceValue(item)}</div>
                      {renderHomoglyphBadges(homoglyphBadges)}
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
                            {renderHistoryValue(item)}
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
                );
              })}
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
                  {preparedRows.map((item) => {
                    const {
                      row,
                      isInvalidField,
                      invalidReasons,
                      showDiff,
                      homoglyphBadges,
                      formattedHistory,
                    } = item;

                    return (
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
                            <div className="min-w-0">
                              {renderInvoiceValue(item)}
                            </div>
                            {renderHomoglyphBadges(homoglyphBadges)}
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
                                {renderHistoryValue(item)}
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
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
