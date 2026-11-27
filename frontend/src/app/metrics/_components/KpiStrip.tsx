"use client";

import { Skeleton } from "@/components/ui/skeleton";
import type { Dictionary, Lang } from "@/i18n";
import { formatIntegerForLang, formatPercentForLang } from "@/lib/format";
import { cn } from "cn";
import type { InterpolateFn, NormalizedMetrics } from "../_lib/normalize";

interface KpiStripProps {
  metrics: NormalizedMetrics;
  defaultCheckLatencyMs: number;
  lang: Lang;
  t: Dictionary;
  interpolate: InterpolateFn;
}

export function MetricsKpiSkeleton() {
  return (
    <div className="space-y-2.5">
      <div className="ui-kpi-strip">
        {Array.from({ length: 4 }).map((_, idx) => (
          <div
            key={`kpi-skeleton-${idx}`}
            className="ui-kpi-cell justify-start gap-1.5"
          >
            <Skeleton className="h-3.5 w-28 max-w-full rounded-[4px]" />
            <Skeleton className="h-7 w-20 rounded-[4px]" />
            <Skeleton className="h-3.5 w-36 max-w-full rounded-[4px]" />
          </div>
        ))}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 px-0.5">
        <Skeleton className="h-3.5 w-64 max-w-full rounded-[4px]" />
        <Skeleton className="h-5 w-16 rounded-[4px]" />
      </div>
    </div>
  );
}

export function KpiStrip({
  metrics,
  defaultCheckLatencyMs,
  lang,
  t,
  interpolate,
}: KpiStripProps) {
  const effectiveLatencyMs = metrics.checkLatencyMs ?? defaultCheckLatencyMs;
  const hasRedYellowRates =
    metrics.stoppedRedRatePercent !== null ||
    metrics.escalatedYellowRatePercent !== null;

  const hasHistoryAlert = metrics.historyReplay !== null;
  const historyAlertPercent = metrics.historyReplay?.alertRatePercent ?? null;
  const historyFlagged = metrics.historyReplay?.flagged ?? null;
  const historyTotal = metrics.historyReplay?.total ?? null;

  const datasetParts: Array<{ key: string; label: string; value: string }> = [];
  if (metrics.total !== null) {
    datasetParts.push({
      key: "total",
      label: t.metrics.tiles.total,
      value: formatIntegerForLang(metrics.total, lang),
    });
  }
  if (metrics.attacks !== null) {
    datasetParts.push({
      key: "attacks",
      label: t.metrics.tiles.attacks,
      value: formatIntegerForLang(metrics.attacks, lang),
    });
  }
  if (metrics.legit !== null) {
    datasetParts.push({
      key: "legit",
      label: t.metrics.tiles.legit,
      value: formatIntegerForLang(metrics.legit, lang),
    });
  }

  return (
    <div className="space-y-2.5">
      <div className="ui-kpi-strip">
        {/* 1. Attacks detected */}
        <div className="ui-kpi-cell justify-start gap-1">
          <span className="ui-kpi-label">{t.metrics.kpiDetectedLabel}</span>
          <div className="ui-kpi-value text-[var(--brand-text)]">
            {formatPercentForLang(metrics.detectionRatePercent, lang)}
          </div>
          {hasRedYellowRates ? (
            <div className="flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5 text-xs text-muted-foreground tabular-nums">
              {metrics.stoppedRedRatePercent !== null && (
                <span className="inline-flex items-baseline gap-1">
                  <span>{t.metrics.kpiStoppedShort}</span>
                  <span className="font-semibold text-[var(--status-danger-text)]">
                    {formatPercentForLang(metrics.stoppedRedRatePercent, lang)}
                  </span>
                </span>
              )}
              {metrics.stoppedRedRatePercent !== null &&
                metrics.escalatedYellowRatePercent !== null && (
                  <span aria-hidden="true">·</span>
                )}
              {metrics.escalatedYellowRatePercent !== null && (
                <span className="inline-flex items-baseline gap-1">
                  <span>{t.metrics.kpiEscalatedShort}</span>
                  <span className="font-semibold text-[var(--status-warn-text)]">
                    {formatPercentForLang(
                      metrics.escalatedYellowRatePercent,
                      lang
                    )}
                  </span>
                </span>
              )}
            </div>
          ) : (
            metrics.detectedAttacksCount !== null &&
            metrics.attacks !== null && (
              <div className="text-xs text-muted-foreground tabular-nums">
                {interpolate(t.metrics.ofAttacks, {
                  count: formatIntegerForLang(
                    metrics.detectedAttacksCount,
                    lang
                  ),
                  total: formatIntegerForLang(metrics.attacks, lang),
                })}
              </div>
            )
          )}
        </div>

        {/* 2. False alarms on hard set */}
        <div className="ui-kpi-cell justify-start gap-1">
          <span className="ui-kpi-label">{t.metrics.kpiFalseAlarmsLabel}</span>
          <div
            className={cn(
              "ui-kpi-value",
              (metrics.falseAlarmRatePercent ?? 0) > 10 &&
                "text-[var(--status-warn-text)]"
            )}
          >
            {formatPercentForLang(metrics.falseAlarmRatePercent, lang)}
          </div>
          <p className="text-xs leading-4 text-muted-foreground break-words">
            {t.metrics.kpiFalseAlarmsHint}
          </p>
        </div>

        {/* 3. Yearly history alert rate */}
        <div className="ui-kpi-cell justify-start gap-1">
          <span className="ui-kpi-label">{t.metrics.kpiHistoryLabel}</span>
          <div
            className={cn(
              "ui-kpi-value",
              hasHistoryAlert &&
                ((historyAlertPercent ?? 0) > 15
                  ? "text-[var(--status-warn-text)]"
                  : "text-[var(--brand-text)]")
            )}
          >
            {hasHistoryAlert
              ? formatPercentForLang(historyAlertPercent, lang)
              : "—"}
          </div>
          <div className="text-xs text-muted-foreground tabular-nums">
            {hasHistoryAlert && historyFlagged !== null && historyTotal !== null
              ? interpolate(t.metrics.kpiHistorySub, {
                  alerts: formatIntegerForLang(historyFlagged, lang),
                  total: formatIntegerForLang(historyTotal, lang),
                })
              : t.metrics.kpiHistoryUnavailable}
          </div>
        </div>

        {/* 4. Check latency */}
        <div className="ui-kpi-cell justify-start gap-1">
          <span className="ui-kpi-label">{t.metrics.kpiLatencyLabel}</span>
          <div className="ui-kpi-value">
            {interpolate(t.metrics.kpiLatencyValue, {
              ms: formatIntegerForLang(effectiveLatencyMs, lang),
            })}
          </div>
          <p className="text-xs leading-4 text-muted-foreground break-words">
            {t.metrics.kpiLatencyHint}
          </p>
        </div>
      </div>

      {/* Compact dataset composition metadata strip */}
      {(datasetParts.length > 0 || metrics.seed !== null) && (
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5 px-0.5 text-xs text-muted-foreground tabular-nums">
          <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
            {datasetParts.map((part, idx) => (
              <span
                key={part.key}
                className="inline-flex items-baseline gap-1.5"
              >
                {idx > 0 && (
                  <span aria-hidden="true" className="text-border">
                    ·
                  </span>
                )}
                <span>{part.label}:</span>
                <span className="font-medium text-foreground">{part.value}</span>
              </span>
            ))}
          </div>

          {metrics.seed !== null && (
            <span className="ui-tag font-mono tabular-nums">
              {interpolate(t.metrics.seedMeta, { seed: metrics.seed })}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
