"use client";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { Dictionary, Lang } from "@/i18n";
import {
  formatIntegerForLang,
  formatPercentForLang,
  VERDICT_STYLES,
} from "@/lib/format";
import type { Verdict } from "@/lib/types";
import { cn } from "cn";
import {
  computeStackedSegments,
  CORE_VERDICTS,
  HISTORY_VERDICT_ORDER,
  VERDICT_BAR_BG,
  type InterpolateFn,
  type NormalizedHistoryReplay,
} from "../_lib/normalize";

interface HistoryReplayCardProps {
  historyReplay: NormalizedHistoryReplay | null;
  lang: Lang;
  t: Dictionary;
  interpolate: InterpolateFn;
}

export function HistoryReplayCard({
  historyReplay,
  lang,
  t,
  interpolate,
}: HistoryReplayCardProps) {
  const cardTitle =
    historyReplay?.total !== null && historyReplay?.total !== undefined
      ? interpolate(t.metrics.verdictBarTitleWithCount, {
          title: t.metrics.historyReplayTitle,
          count: formatIntegerForLang(historyReplay.total, lang),
        })
      : t.metrics.historyReplayTitle;

  const { total: stackedTotal, segments } = computeStackedSegments(
    historyReplay?.verdicts ?? null,
    HISTORY_VERDICT_ORDER,
    historyReplay?.total,
    1.5
  );

  const invalidCount =
    typeof historyReplay?.verdicts?.invalid === "number" &&
    historyReplay.verdicts.invalid > 0
      ? historyReplay.verdicts.invalid
      : 0;

  const legendVerdicts: Verdict[] =
    invalidCount > 0 ? [...CORE_VERDICTS, "invalid"] : [...CORE_VERDICTS];

  const legendItems = legendVerdicts.map((verdict) => {
    const rawCount = historyReplay?.verdicts?.[verdict];
    const count =
      typeof rawCount === "number" && Number.isFinite(rawCount) && rawCount > 0
        ? rawCount
        : 0;
    const rawPercent = stackedTotal > 0 ? (count / stackedTotal) * 100 : 0;
    return {
      verdict,
      count,
      rawPercent,
      formattedCount: formatIntegerForLang(count, lang),
      formattedPercent: formatPercentForLang(rawPercent, lang),
    };
  });

  const barAriaLabel = interpolate(t.metrics.verdictBarAriaLabel, {
    total: formatIntegerForLang(stackedTotal, lang),
    breakdown: legendItems
      .map((item) =>
        interpolate(t.metrics.verdictBarSegmentAria, {
          label: t.verdicts[item.verdict],
          count: item.formattedCount,
          rate: item.formattedPercent,
        })
      )
      .join(", "),
  });

  return (
    <Card className="min-w-0">
      <CardHeader className="border-b border-border pb-3.5">
        <CardTitle>{cardTitle}</CardTitle>
        <CardDescription className="mt-0.5">
          {t.metrics.historyReplaySubtitle}
        </CardDescription>
      </CardHeader>

      <CardContent>
        {!historyReplay ? (
          <p className="text-sm text-muted-foreground">
            {t.metrics.historyReplayUnavailable}
          </p>
        ) : (
          <div className="space-y-4">
            {/* Compact summary metrics above the stacked bar */}
            <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                <span className="text-xs font-medium text-muted-foreground">
                  {t.metrics.historyReplayTotal}:
                </span>
                <span className="text-base font-semibold text-foreground tabular-nums">
                  {formatIntegerForLang(historyReplay.total, lang)}
                </span>
              </div>

              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                <span className="text-xs font-medium text-muted-foreground">
                  {t.metrics.historyReplayAlertRate}:
                </span>
                <span
                  className={cn(
                    "text-base font-semibold tabular-nums",
                    (historyReplay.alertRatePercent ?? 0) > 15
                      ? "text-[var(--status-warn-text)]"
                      : "text-[var(--brand-text)]"
                  )}
                >
                  {formatPercentForLang(historyReplay.alertRatePercent, lang)}
                </span>
                {historyReplay.flagged !== null &&
                  historyReplay.total !== null && (
                    <span className="text-xs text-muted-foreground tabular-nums">
                      (
                      {interpolate(t.metrics.historyReplayFlagged, {
                        alerts: formatIntegerForLang(
                          historyReplay.flagged,
                          lang
                        ),
                        total: formatIntegerForLang(historyReplay.total, lang),
                      })}
                      )
                    </span>
                  )}
              </div>
            </div>

            {/* Stacked verdict distribution bar */}
            {historyReplay.verdicts && segments.length > 0 && (
              <div className="space-y-3">
                <div
                  role="img"
                  aria-label={barAriaLabel}
                  className="flex h-3.5 w-full overflow-hidden rounded-[4px] bg-muted sm:h-4"
                >
                  {segments.map((segment) => {
                    const label = interpolate(t.metrics.verdictBarSegmentAria, {
                      label: t.verdicts[segment.verdict],
                      count: formatIntegerForLang(segment.count, lang),
                      rate: formatPercentForLang(segment.rawPercent, lang),
                    });
                    return (
                      <div
                        key={segment.verdict}
                        title={label}
                        className={cn(
                          "h-full border-r border-card transition-all duration-300 last:border-r-0",
                          VERDICT_BAR_BG[segment.verdict]
                        )}
                        style={{ width: `${segment.visualWidthPercent}%` }}
                      />
                    );
                  })}
                </div>

                {/* Full verdict legend (all four core verdicts always shown) */}
                <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
                  {legendItems.map((item) => {
                    const style = VERDICT_STYLES[item.verdict];
                    const isZero = item.count === 0;
                    return (
                      <span
                        key={item.verdict}
                        className="ui-status text-xs leading-5"
                      >
                        <span
                          aria-hidden="true"
                          className={cn("ui-status-dot", style.dotClass)}
                        />
                        <span className="text-[var(--text-secondary)]">
                          {t.verdicts[item.verdict]}:
                        </span>
                        <span
                          className={cn(
                            "font-semibold tabular-nums",
                            isZero ? "text-muted-foreground" : "text-foreground"
                          )}
                        >
                          {item.formattedCount}
                        </span>
                        <span className="text-muted-foreground tabular-nums">
                          ({item.formattedPercent})
                        </span>
                      </span>
                    );
                  })}
                </div>

                <p className="flex items-start gap-2 text-xs leading-5 text-muted-foreground">
                  <span
                    aria-hidden="true"
                    className={cn(
                      "ui-status-dot mt-1.5",
                      VERDICT_STYLES.grey.dotClass
                    )}
                  />
                  <span>{t.metrics.verdictBarGreyNote}</span>
                </p>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
