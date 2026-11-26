"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { useT } from "@/i18n";
import { localizeBackendText, pickReason } from "@/lib/format";
import type { Signal, SignalSeverity } from "@/lib/types";
import { cn } from "cn";

interface ReasonsListProps {
  signals: Signal[];
  score?: number;
  className?: string;
}

const SEVERITY_DOT_CLASS: Record<SignalSeverity, string> = {
  block: "ui-dot-danger",
  primary: "ui-dot-danger",
  amplifier: "ui-dot-warn",
  info: "ui-dot-neutral",
};

export function ReasonsList({ signals, score, className }: ReasonsListProps) {
  const { t, lang, formatDate, interpolate } = useT();
  const [detailsOpen, setDetailsOpen] = useState(false);

  const orderedSignals = signals ?? [];
  const topReasons = orderedSignals.slice(0, 4);
  const hiddenCount = Math.max(0, orderedSignals.length - topReasons.length);

  const signalRulesMap: Record<string, string> = t.signalRules;
  const fieldLabelsMap: Record<string, string> = t.fields;

  return (
    <Card className={cn("min-w-0", className)}>
      <CardHeader className="border-b border-border pb-3">
        <CardTitle>{t.reasons.title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {topReasons.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t.reasons.empty}</p>
        ) : (
          <ul className="space-y-2">
            {topReasons.map((signal, idx) => {
              const isPositiveSignal =
                signal.rule_id === "trusted_account" ||
                signal.rule_id === "budget_payment" ||
                signal.rule_id === "bank_confirmed_account";
              return (
                <li
                  key={`${signal.rule_id}-${idx}`}
                  className="flex min-w-0 items-start gap-2.5 text-sm leading-5 text-foreground"
                >
                  <span
                    aria-hidden="true"
                    className={cn(
                      "mt-[7px] size-1.5 shrink-0 rounded-full",
                      isPositiveSignal
                        ? "ui-dot-ok"
                        : SEVERITY_DOT_CLASS[signal.severity] ?? "ui-dot-neutral"
                    )}
                  />
                  <span className="min-w-0 break-words">
                    {pickReason(signal, lang)}
                  </span>
                </li>
              );
            })}
          </ul>
        )}

        {orderedSignals.length > 0 && (
          <Collapsible open={detailsOpen} onOpenChange={setDetailsOpen}>
            <CollapsibleTrigger
              render={
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="min-h-10 gap-1.5 px-2 text-xs font-medium text-muted-foreground hover:text-foreground sm:min-h-8"
                />
              }
            >
              <span>
                {hiddenCount > 0
                  ? interpolate(t.reasons.moreDetailsHidden, {
                      count: hiddenCount,
                    })
                  : t.reasons.moreDetails}
              </span>
              <ChevronDown
                className={cn(
                  "size-3.5 transition-transform duration-150",
                  detailsOpen && "rotate-180"
                )}
              />
            </CollapsibleTrigger>

            <CollapsibleContent className="ui-subpanel mt-2.5 space-y-2.5">
              {score !== undefined && (
                <div className="flex items-center justify-between gap-2 border-b border-border pb-2 text-xs">
                  <span className="font-medium text-muted-foreground">
                    {t.reasons.totalRiskScore}
                  </span>
                  <span className="shrink-0 font-mono font-semibold tabular-nums text-foreground">
                    {score} / 100
                  </span>
                </div>
              )}

              <div className="space-y-2">
                {orderedSignals.map((signal, idx) => {
                  const ruleTitle =
                    signalRulesMap[signal.rule_id] ?? t.reasons.unknownSignal;
                  const isExtra = idx >= 4;
                  const evidenceFieldLabel = signal.evidence
                    ? fieldLabelsMap[signal.evidence.field] ??
                      signal.evidence.field
                    : null;

                  return (
                    <div
                      key={`${signal.rule_id}-detail-${idx}`}
                      className="min-w-0 space-y-1.5 rounded-[6px] border border-border bg-card p-3 text-xs"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex min-w-0 flex-wrap items-center gap-1.5">
                          <span className="font-semibold text-foreground break-words">
                            {ruleTitle}
                          </span>
                          <span className="ui-tag">
                            {t.severity[signal.severity] ?? signal.severity}
                          </span>
                          {isExtra && (
                            <span className="ui-tag">
                              {t.reasons.extraBadge}
                            </span>
                          )}
                        </div>
                        <span className="shrink-0 font-mono font-semibold tabular-nums text-foreground">
                          {signal.points > 0
                            ? `+${signal.points}`
                            : signal.points}{" "}
                          {t.reasons.pointsSuffix}
                        </span>
                      </div>

                      <p className="text-sm text-foreground break-words">
                        {pickReason(signal, lang)}
                      </p>

                      {signal.evidence && (
                        <div className="grid grid-cols-1 gap-1.5 rounded-[4px] bg-muted/60 px-2.5 py-2 font-mono text-[11px] tabular-nums text-muted-foreground sm:grid-cols-2">
                          <div className="min-w-0 break-words">
                            <span className="text-[var(--text-secondary)]">
                              {t.reasons.evidenceField}
                            </span>
                            {evidenceFieldLabel}
                          </div>
                          {signal.evidence.since && (
                            <div className="min-w-0">
                              <span className="text-[var(--text-secondary)]">
                                {t.reasons.evidenceSince}
                              </span>
                              {formatDate(signal.evidence.since)}
                            </div>
                          )}
                          {signal.evidence.expected !== null && (
                            <div className="min-w-0 break-all">
                              <span className="text-[var(--text-secondary)]">
                                {t.reasons.evidenceExpected}
                              </span>
                              {localizeBackendText(
                                signal.evidence.expected,
                                lang
                              )}
                            </div>
                          )}
                          {signal.evidence.actual !== null && (
                            <div className="min-w-0 break-all">
                              <span className="text-[var(--text-secondary)]">
                                {t.reasons.evidenceActual}
                              </span>
                              {localizeBackendText(
                                signal.evidence.actual,
                                lang
                              )}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </CollapsibleContent>
          </Collapsible>
        )}
      </CardContent>
    </Card>
  );
}
