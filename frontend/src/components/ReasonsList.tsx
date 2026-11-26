"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { useT } from "@/i18n";
import { pickReason } from "@/lib/format";
import type { Signal, SignalSeverity } from "@/lib/types";
import { cn } from "cn";

interface ReasonsListProps {
  signals: Signal[];
  score?: number;
  className?: string;
}

const SEVERITY_DOT_CLASS: Record<SignalSeverity, string> = {
  block: "bg-red-600",
  primary: "bg-red-500",
  amplifier: "bg-amber-500",
  info: "bg-[#737376]",
};

export function ReasonsList({ signals, score, className }: ReasonsListProps) {
  const { t, formatDate, interpolate } = useT();
  const [detailsOpen, setDetailsOpen] = useState(false);

  const orderedSignals = signals ?? [];
  const topReasons = orderedSignals.slice(0, 4);
  const hiddenCount = Math.max(0, orderedSignals.length - topReasons.length);

  const signalRulesMap: Record<string, string> = t.signalRules;

  return (
    <Card className={cn("min-w-0", className)}>
      <CardHeader className="border-b border-border pb-3.5">
        <CardTitle className="text-base font-semibold">
          {t.reasons.title}
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-4 space-y-4">
        {topReasons.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t.reasons.empty}</p>
        ) : (
          <ul className="space-y-2.5">
            {topReasons.map((signal, idx) => {
              const isTrustedSignal = signal.rule_id === "trusted_account";
              return (
                <li
                  key={`${signal.rule_id}-${idx}`}
                  className="flex min-w-0 items-start gap-3 text-sm leading-relaxed text-foreground"
                >
                  <span
                    aria-hidden="true"
                    className={cn(
                      "mt-2 size-2 shrink-0 rounded-full",
                      isTrustedSignal
                        ? "bg-[#00AB75]"
                        : SEVERITY_DOT_CLASS[signal.severity] ?? "bg-[#737376]"
                    )}
                  />
                  <span className="min-w-0 break-words">
                    {pickReason(signal)}
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
                  className="min-h-11 gap-1.5 px-2.5 text-xs font-medium text-muted-foreground hover:text-foreground sm:min-h-8 sm:px-2"
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

            <CollapsibleContent className="mt-3 space-y-3 rounded-xl border border-border bg-background/80 p-3 sm:p-3.5">
              {score !== undefined && (
                <div className="flex items-center justify-between gap-2 border-b border-border pb-2 text-xs">
                  <span className="font-medium text-muted-foreground">
                    {t.reasons.totalRiskScore}
                  </span>
                  <span className="shrink-0 font-mono font-semibold text-foreground">
                    {score} / 100
                  </span>
                </div>
              )}

              <div className="space-y-2.5">
                {orderedSignals.map((signal, idx) => {
                  const ruleLabel = signalRulesMap[signal.rule_id];
                  const isExtra = idx >= 4;
                  return (
                    <div
                      key={`${signal.rule_id}-detail-${idx}`}
                      className="min-w-0 rounded-lg border border-border bg-card p-3 text-xs space-y-1.5"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex min-w-0 flex-wrap items-center gap-1.5 sm:gap-2">
                          <Badge
                            variant="outline"
                            className="h-auto max-w-full whitespace-normal break-all font-mono text-[11px] px-1.5 py-0.5"
                          >
                            {signal.rule_id}
                          </Badge>
                          {ruleLabel && (
                            <span className="font-medium text-foreground break-words">
                              {ruleLabel}
                            </span>
                          )}
                          <span className="text-muted-foreground">
                            {t.severity[signal.severity] ?? signal.severity}
                          </span>
                          {isExtra && (
                            <Badge
                              variant="secondary"
                              className="h-auto text-[10px] px-1.5 py-0.5"
                            >
                              {t.reasons.extraBadge}
                            </Badge>
                          )}
                        </div>
                        <span className="shrink-0 font-mono font-semibold text-foreground">
                          {signal.points > 0
                            ? `+${signal.points}`
                            : signal.points}{" "}
                          {t.reasons.pointsSuffix}
                        </span>
                      </div>

                      <p className="text-sm text-foreground break-words">
                        {pickReason(signal)}
                      </p>

                      {signal.evidence && (
                        <div className="grid grid-cols-1 gap-1.5 rounded bg-muted/60 px-2.5 py-2 font-mono text-[11px] text-muted-foreground sm:grid-cols-2">
                          <div className="min-w-0 break-words">
                            <span className="text-foreground/70">
                              {t.reasons.evidenceField}
                            </span>
                            {signal.evidence.field}
                          </div>
                          {signal.evidence.since && (
                            <div className="min-w-0">
                              <span className="text-foreground/70">
                                {t.reasons.evidenceSince}
                              </span>
                              {formatDate(signal.evidence.since)}
                            </div>
                          )}
                          {signal.evidence.expected !== null && (
                            <div className="min-w-0 break-all">
                              <span className="text-foreground/70">
                                {t.reasons.evidenceExpected}
                              </span>
                              {signal.evidence.expected}
                            </div>
                          )}
                          {signal.evidence.actual !== null && (
                            <div className="min-w-0 break-all">
                              <span className="text-foreground/70">
                                {t.reasons.evidenceActual}
                              </span>
                              {signal.evidence.actual}
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
