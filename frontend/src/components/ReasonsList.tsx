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
import { formatDateRu, SIGNAL_RULE_LABELS } from "@/lib/format";
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
  info: "bg-slate-400",
};

const SEVERITY_LABEL_RU: Record<SignalSeverity, string> = {
  block: "Блокирующий факт",
  primary: "Основной сигнал",
  amplifier: "Усиливающий признак",
  info: "Информация",
};

export function ReasonsList({ signals, score, className }: ReasonsListProps) {
  const [detailsOpen, setDetailsOpen] = useState(false);

  const orderedSignals = signals ?? [];
  const topReasons = orderedSignals.slice(0, 4);
  const hiddenCount = Math.max(0, orderedSignals.length - topReasons.length);

  return (
    <Card className={cn("min-w-0 border-border shadow-xs", className)}>
      <CardHeader className="border-b border-border pb-3.5">
        <CardTitle className="text-base font-semibold">Почему</CardTitle>
      </CardHeader>
      <CardContent className="pt-4 space-y-4">
        {topReasons.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Отклонений и подозрительных признаков не выявлено.
          </p>
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
                        ? "bg-emerald-600"
                        : SEVERITY_DOT_CLASS[signal.severity] ?? "bg-slate-400"
                    )}
                  />
                  <span className="min-w-0 break-words">{signal.reason_ru}</span>
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
                  ? `Подробнее (ещё ${hiddenCount})`
                  : "Подробнее"}
              </span>
              <ChevronDown
                className={cn(
                  "size-3.5 transition-transform duration-150",
                  detailsOpen && "rotate-180"
                )}
              />
            </CollapsibleTrigger>

            <CollapsibleContent className="mt-3 space-y-3 rounded-lg border border-border bg-muted/40 p-3 sm:p-3.5">
              {score !== undefined && (
                <div className="flex items-center justify-between gap-2 border-b border-border pb-2 text-xs">
                  <span className="font-medium text-muted-foreground">
                    Суммарный балл риска
                  </span>
                  <span className="shrink-0 font-mono font-semibold text-foreground">
                    {score} / 100
                  </span>
                </div>
              )}

              <div className="space-y-2.5">
                {orderedSignals.map((signal, idx) => {
                  const ruleLabel = SIGNAL_RULE_LABELS[signal.rule_id];
                  const isExtra = idx >= 4;
                  return (
                    <div
                      key={`${signal.rule_id}-detail-${idx}`}
                      className="min-w-0 rounded-md border border-border bg-card p-3 text-xs space-y-1.5"
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
                            {SEVERITY_LABEL_RU[signal.severity] ??
                              signal.severity}
                          </span>
                          {isExtra && (
                            <Badge
                              variant="secondary"
                              className="h-auto text-[10px] px-1.5 py-0.5"
                            >
                              Дополнительно
                            </Badge>
                          )}
                        </div>
                        <span className="shrink-0 font-mono font-semibold text-foreground">
                          {signal.points > 0
                            ? `+${signal.points}`
                            : signal.points}{" "}
                          б.
                        </span>
                      </div>

                      <p className="text-sm text-foreground break-words">
                        {signal.reason_ru}
                      </p>

                      {signal.evidence && (
                        <div className="grid grid-cols-1 gap-1.5 rounded bg-muted/50 px-2.5 py-2 font-mono text-[11px] text-muted-foreground sm:grid-cols-2">
                          <div className="min-w-0 break-words">
                            <span className="text-foreground/70">Поле: </span>
                            {signal.evidence.field}
                          </div>
                          {signal.evidence.since && (
                            <div className="min-w-0">
                              <span className="text-foreground/70">
                                С даты:{" "}
                              </span>
                              {formatDateRu(signal.evidence.since)}
                            </div>
                          )}
                          {signal.evidence.expected !== null && (
                            <div className="min-w-0 break-all">
                              <span className="text-foreground/70">
                                Ожидалось:{" "}
                              </span>
                              {signal.evidence.expected}
                            </div>
                          )}
                          {signal.evidence.actual !== null && (
                            <div className="min-w-0 break-all">
                              <span className="text-foreground/70">
                                Получено:{" "}
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
