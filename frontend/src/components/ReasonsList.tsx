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
import { formatDateRu } from "@/lib/format";
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

  const sortedSignals = [...signals].sort((a, b) => b.points - a.points);
  const topReasons = sortedSignals.slice(0, 4);

  return (
    <Card className={cn("border-border shadow-xs", className)}>
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
            {topReasons.map((signal, idx) => (
              <li
                key={`${signal.rule_id}-${idx}`}
                className="flex items-start gap-3 text-sm leading-relaxed text-foreground"
              >
                <span
                  aria-hidden="true"
                  className={cn(
                    "mt-2 size-2 shrink-0 rounded-full",
                    SEVERITY_DOT_CLASS[signal.severity] ?? "bg-slate-400"
                  )}
                />
                <span>{signal.reason_ru}</span>
              </li>
            ))}
          </ul>
        )}

        {sortedSignals.length > 0 && (
          <Collapsible open={detailsOpen} onOpenChange={setDetailsOpen}>
            <CollapsibleTrigger
              render={
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="gap-1.5 px-2 text-xs font-medium text-muted-foreground hover:text-foreground"
                />
              }
            >
              <span>Подробнее</span>
              <ChevronDown
                className={cn(
                  "size-3.5 transition-transform duration-150",
                  detailsOpen && "rotate-180"
                )}
              />
            </CollapsibleTrigger>

            <CollapsibleContent className="mt-3 space-y-3 rounded-lg border border-border bg-muted/40 p-3.5">
              {score !== undefined && (
                <div className="flex items-center justify-between border-b border-border pb-2 text-xs">
                  <span className="font-medium text-muted-foreground">
                    Суммарный балл риска
                  </span>
                  <span className="font-mono font-semibold text-foreground">
                    {score} / 100
                  </span>
                </div>
              )}

              <div className="space-y-2.5">
                {sortedSignals.map((signal, idx) => (
                  <div
                    key={`${signal.rule_id}-detail-${idx}`}
                    className="rounded-md border border-border bg-card p-3 text-xs space-y-1.5"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <Badge
                          variant="outline"
                          className="font-mono text-[11px] px-1.5 py-0"
                        >
                          {signal.rule_id}
                        </Badge>
                        <span className="text-muted-foreground">
                          {SEVERITY_LABEL_RU[signal.severity] ?? signal.severity}
                        </span>
                      </div>
                      <span className="font-mono font-semibold text-foreground">
                        {signal.points > 0 ? `+${signal.points}` : signal.points}{" "}
                        б.
                      </span>
                    </div>

                    <p className="text-sm text-foreground">{signal.reason_ru}</p>

                    {signal.evidence && (
                      <div className="grid grid-cols-1 gap-1 rounded bg-muted/50 px-2.5 py-2 font-mono text-[11px] text-muted-foreground sm:grid-cols-2">
                        <div>
                          <span className="text-foreground/70">Поле: </span>
                          {signal.evidence.field}
                        </div>
                        {signal.evidence.since && (
                          <div>
                            <span className="text-foreground/70">С даты: </span>
                            {formatDateRu(signal.evidence.since)}
                          </div>
                        )}
                        {signal.evidence.expected !== null && (
                          <div className="break-all">
                            <span className="text-foreground/70">Ожидалось: </span>
                            {signal.evidence.expected}
                          </div>
                        )}
                        {signal.evidence.actual !== null && (
                          <div className="break-all">
                            <span className="text-foreground/70">Получено: </span>
                            {signal.evidence.actual}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </CollapsibleContent>
          </Collapsible>
        )}
      </CardContent>
    </Card>
  );
}
