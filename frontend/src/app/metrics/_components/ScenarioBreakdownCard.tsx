"use client";

import { useId, useRef, useState, type KeyboardEvent } from "react";
import { AlertTriangle } from "lucide-react";
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
  ATTACK_VERDICT_ORDER,
  collectBlindSpots,
  computeStackedSegments,
  CORE_VERDICTS,
  LEGIT_VERDICT_ORDER,
  VERDICT_BAR_BG,
  WARN_TAG_CLASS,
  type BlindSpotThresholds,
  type InterpolateFn,
  type NormalizedKindRow,
} from "../_lib/normalize";

type ScenarioTab = "attacks" | "legit";

interface ScenarioBreakdownCardProps {
  byKind: NormalizedKindRow[];
  totalAttacks: number | null;
  totalLegit: number | null;
  thresholds: BlindSpotThresholds;
  lang: Lang;
  t: Dictionary;
  interpolate: InterpolateFn;
}

function getVerdictCount(row: NormalizedKindRow, verdict: Verdict): number {
  switch (verdict) {
    case "green":
      return row.greenCount;
    case "grey":
      return row.greyCount;
    case "yellow":
      return row.yellowCount;
    case "red":
      return row.redCount;
    case "invalid":
      return row.invalidCount;
  }
}

interface ScenarioRowBarProps {
  row: NormalizedKindRow;
  order: readonly Verdict[];
  formattedRate: string;
  lang: Lang;
  t: Dictionary;
  interpolate: InterpolateFn;
}

function ScenarioRowBar({
  row,
  order,
  formattedRate,
  lang,
  t,
  interpolate,
}: ScenarioRowBarProps) {
  const percent = row.ratePercent ?? 0;
  const { segments } = computeStackedSegments(
    row.verdicts,
    order,
    row.count,
    1.5
  );
  const showStacked = row.hasVerdictSplit && segments.length > 0;

  const fallbackBarColorClass = row.isFalsePositiveMetric
    ? percent > 15
      ? "bg-[var(--status-warn)]"
      : "bg-[var(--status-neutral)]"
    : percent >= 80
      ? "bg-primary"
      : percent >= 50
        ? "bg-[var(--status-warn)]"
        : "bg-[var(--status-danger)]";

  return (
    <div
      role="progressbar"
      aria-valuenow={Math.round(percent)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={interpolate(t.metrics.ariaBarLabel, {
        name: row.title,
        rate: formattedRate,
      })}
      className="flex h-2.5 w-full overflow-hidden rounded-[3px] bg-muted"
    >
      {showStacked ? (
        segments.map((segment) => {
          const tooltip = interpolate(t.metrics.verdictBarSegmentAria, {
            label: t.verdicts[segment.verdict],
            count: formatIntegerForLang(segment.count, lang),
            rate: formatPercentForLang(segment.rawPercent, lang),
          });
          return (
            <div
              key={segment.verdict}
              title={tooltip}
              className={cn(
                "h-full border-r border-card transition-all duration-300 last:border-r-0",
                VERDICT_BAR_BG[segment.verdict]
              )}
              style={{ width: `${segment.visualWidthPercent}%` }}
            />
          );
        })
      ) : (
        <div
          className={cn(
            "h-full transition-all duration-300",
            fallbackBarColorClass
          )}
          style={{ width: `${percent}%` }}
        />
      )}
    </div>
  );
}

interface RowVerdictCountsProps {
  row: NormalizedKindRow;
  order: readonly Verdict[];
  showZeroCore: boolean;
  lang: Lang;
  t: Dictionary;
  interpolate: InterpolateFn;
}

function RowVerdictCounts({
  row,
  order,
  showZeroCore,
  lang,
  t,
  interpolate,
}: RowVerdictCountsProps) {
  if (!row.hasVerdictSplit) {
    return null;
  }

  const visibleVerdicts = order.filter((verdict) => {
    const count = getVerdictCount(row, verdict);
    if (verdict === "invalid") return count > 0;
    return showZeroCore || count > 0;
  });

  if (visibleVerdicts.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-wrap items-center gap-x-3.5 gap-y-1 text-xs tabular-nums">
      {visibleVerdicts.map((verdict) => {
        const count = getVerdictCount(row, verdict);
        const style = VERDICT_STYLES[verdict];
        const countColorClass =
          count === 0
            ? "text-muted-foreground"
            : verdict === "red"
              ? "font-medium text-[var(--status-danger-text)]"
              : verdict === "yellow"
                ? "font-medium text-[var(--status-warn-text)]"
                : "font-medium text-foreground";

        return (
          <span
            key={verdict}
            className="inline-flex items-center gap-1.5 text-muted-foreground"
          >
            <span
              aria-hidden="true"
              className={cn("ui-status-dot", style.dotClass)}
            />
            <span className={countColorClass}>
              {interpolate(t.metrics.tabsVerdictCount, {
                label: t.verdicts[verdict],
                count: formatIntegerForLang(count, lang),
              })}
            </span>
          </span>
        );
      })}
    </div>
  );
}

function TabLegend({
  order,
  t,
}: {
  order: readonly Verdict[];
  t: Dictionary;
}) {
  const coreOrder = order.filter((v) => CORE_VERDICTS.includes(v));
  return (
    <div
      aria-hidden="true"
      className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-border pb-2.5 text-xs text-muted-foreground"
    >
      {coreOrder.map((verdict) => (
        <span key={verdict} className="inline-flex items-center gap-1.5">
          <span
            className={cn("ui-status-dot", VERDICT_STYLES[verdict].dotClass)}
          />
          <span>{t.verdicts[verdict]}</span>
        </span>
      ))}
    </div>
  );
}

export function ScenarioBreakdownCard({
  byKind,
  totalAttacks,
  totalLegit,
  thresholds,
  lang,
  t,
  interpolate,
}: ScenarioBreakdownCardProps) {
  const [activeTab, setActiveTab] = useState<ScenarioTab>("attacks");
  const baseId = useId();
  const attacksTabRef = useRef<HTMLButtonElement>(null);
  const legitTabRef = useRef<HTMLButtonElement>(null);

  const attackRows = byKind.filter((row) => row.category !== "legit");
  const legitRows = byKind.filter((row) => row.category === "legit");

  const attackCountForTab =
    totalAttacks ?? attackRows.reduce((acc, row) => acc + row.count, 0);
  const legitCountForTab =
    totalLegit ?? legitRows.reduce((acc, row) => acc + row.count, 0);

  const blindSpots = collectBlindSpots(byKind);

  const attacksTabId = `${baseId}-tab-attacks`;
  const legitTabId = `${baseId}-tab-legit`;
  const attacksPanelId = `${baseId}-panel-attacks`;
  const legitPanelId = `${baseId}-panel-legit`;

  const switchTab = (next: ScenarioTab, moveFocus: boolean) => {
    setActiveTab(next);
    if (moveFocus) {
      const targetRef = next === "attacks" ? attacksTabRef : legitTabRef;
      targetRef.current?.focus();
    }
  };

  const handleTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
      event.preventDefault();
      switchTab(activeTab === "attacks" ? "legit" : "attacks", true);
    } else if (event.key === "Home") {
      event.preventDefault();
      switchTab("attacks", true);
    } else if (event.key === "End") {
      event.preventDefault();
      switchTab("legit", true);
    }
  };

  return (
    <Card className="min-w-0">
      <CardHeader className="gap-0 pb-0">
        <div className="space-y-0.5 pb-3">
          <CardTitle>{t.metrics.byKindTitle}</CardTitle>
          <CardDescription>{t.metrics.byKindSubtitle}</CardDescription>
        </div>

        {/* Hand-rolled accessible tabs */}
        <div
          role="tablist"
          aria-label={t.metrics.tabsAriaLabel}
          className="ui-tabs no-scrollbar -mx-(--card-spacing) px-(--card-spacing)"
        >
          <button
            ref={attacksTabRef}
            id={attacksTabId}
            type="button"
            role="tab"
            aria-selected={activeTab === "attacks"}
            aria-controls={attacksPanelId}
            tabIndex={activeTab === "attacks" ? 0 : -1}
            onClick={() => switchTab("attacks", false)}
            onKeyDown={handleTabKeyDown}
            className="ui-tab"
          >
            <span>
              {interpolate(t.metrics.tabsAttacks, {
                count: formatIntegerForLang(attackCountForTab, lang),
              })}
            </span>
          </button>

          <button
            ref={legitTabRef}
            id={legitTabId}
            type="button"
            role="tab"
            aria-selected={activeTab === "legit"}
            aria-controls={legitPanelId}
            tabIndex={activeTab === "legit" ? 0 : -1}
            onClick={() => switchTab("legit", false)}
            onKeyDown={handleTabKeyDown}
            className="ui-tab"
          >
            <span>
              {interpolate(t.metrics.tabsLegit, {
                count: formatIntegerForLang(legitCountForTab, lang),
              })}
            </span>
          </button>
        </div>
      </CardHeader>

      <CardContent>
        {byKind.length === 0 ? (
          <div className="ui-empty px-0">
            <p className="ui-empty-desc">{t.metrics.byKindEmpty}</p>
          </div>
        ) : activeTab === "attacks" ? (
          <div
            role="tabpanel"
            id={attacksPanelId}
            aria-labelledby={attacksTabId}
            className="space-y-4"
          >
            {attackRows.length === 0 ? (
              <div className="ui-empty px-0">
                <p className="ui-empty-desc">{t.metrics.tabsAttacksEmpty}</p>
              </div>
            ) : (
              <>
                <TabLegend order={ATTACK_VERDICT_ORDER} t={t} />
                <div className="space-y-4">
                  {attackRows.map((row) => {
                    const formattedRate = formatPercentForLang(
                      row.ratePercent,
                      lang
                    );
                    return (
                      <div key={row.key} className="space-y-1.5">
                        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-sm">
                          <div className="flex min-w-0 flex-wrap items-center gap-2">
                            <span className="font-medium text-foreground break-words">
                              {row.title}
                            </span>
                            {row.isAttackBlindSpot && (
                              <span className={WARN_TAG_CLASS}>
                                <AlertTriangle
                                  className="size-3 shrink-0"
                                  aria-hidden="true"
                                />
                                <span>{t.metrics.blindTagWeakDetection}</span>
                              </span>
                            )}
                          </div>

                          <div className="flex shrink-0 flex-wrap items-center gap-x-2.5 gap-y-0.5 text-xs tabular-nums">
                            <span className="text-muted-foreground">
                              {interpolate(t.metrics.tabsDetectedOfTotal, {
                                detected: formatIntegerForLang(
                                  row.detected,
                                  lang
                                ),
                                total: formatIntegerForLang(row.count, lang),
                              })}
                            </span>
                            <span
                              className={cn(
                                "font-semibold",
                                row.isAttackBlindSpot
                                  ? "text-[var(--status-warn-text)]"
                                  : "text-foreground"
                              )}
                            >
                              {formattedRate}
                            </span>
                          </div>
                        </div>

                        <ScenarioRowBar
                          row={row}
                          order={ATTACK_VERDICT_ORDER}
                          formattedRate={formattedRate}
                          lang={lang}
                          t={t}
                          interpolate={interpolate}
                        />

                        <RowVerdictCounts
                          row={row}
                          order={ATTACK_VERDICT_ORDER}
                          showZeroCore={false}
                          lang={lang}
                          t={t}
                          interpolate={interpolate}
                        />
                      </div>
                    );
                  })}
                </div>
              </>
            )}
          </div>
        ) : (
          <div
            role="tabpanel"
            id={legitPanelId}
            aria-labelledby={legitTabId}
            className="space-y-6"
          >
            {legitRows.length === 0 ? (
              <div className="ui-empty px-0">
                <p className="ui-empty-desc">{t.metrics.tabsLegitEmpty}</p>
              </div>
            ) : (
              <div className="space-y-4">
                <TabLegend order={LEGIT_VERDICT_ORDER} t={t} />
                <div className="space-y-4">
                  {legitRows.map((row) => {
                    const formattedRate = formatPercentForLang(
                      row.ratePercent,
                      lang
                    );
                    return (
                      <div key={row.key} className="space-y-1.5">
                        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-sm">
                          <div className="flex min-w-0 flex-wrap items-center gap-2">
                            <span className="font-medium text-foreground break-words">
                              {row.title}
                            </span>
                            {row.isFalseAlarmHotspot && (
                              <span className={WARN_TAG_CLASS}>
                                <AlertTriangle
                                  className="size-3 shrink-0"
                                  aria-hidden="true"
                                />
                                <span>{t.metrics.blindTagFalseAlarm}</span>
                              </span>
                            )}
                            {row.isNoHistoryKind && (
                              <span className={WARN_TAG_CLASS}>
                                <span>{t.metrics.blindTagNoHistory}</span>
                              </span>
                            )}
                          </div>

                          <div className="flex shrink-0 flex-wrap items-center gap-x-2.5 gap-y-0.5 text-xs tabular-nums">
                            <span className="text-muted-foreground">
                              {interpolate(t.metrics.tabsFalsePositiveCount, {
                                flagged: formatIntegerForLang(
                                  row.detected,
                                  lang
                                ),
                                total: formatIntegerForLang(row.count, lang),
                              })}
                            </span>
                            <span
                              className={cn(
                                "font-semibold",
                                row.isFalseAlarmHotspot
                                  ? "text-[var(--status-warn-text)]"
                                  : "text-foreground"
                              )}
                            >
                              {interpolate(t.metrics.tabsFalsePositiveRate, {
                                rate: formattedRate,
                              })}
                            </span>
                          </div>
                        </div>

                        <ScenarioRowBar
                          row={row}
                          order={LEGIT_VERDICT_ORDER}
                          formattedRate={formattedRate}
                          lang={lang}
                          t={t}
                          interpolate={interpolate}
                        />

                        <RowVerdictCounts
                          row={row}
                          order={LEGIT_VERDICT_ORDER}
                          showZeroCore={true}
                          lang={lang}
                          t={t}
                          interpolate={interpolate}
                        />
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Computed blind spots block */}
            {blindSpots.totalCount === 0 ? (
              <div className="rounded-[6px] border border-border bg-muted/50 p-4">
                <div className="text-sm font-semibold text-foreground">
                  {t.metrics.blindTitle}
                </div>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">
                  {t.metrics.blindEmpty}
                </p>
              </div>
            ) : (
              <section
                aria-label={t.metrics.blindTitle}
                className="space-y-4 rounded-[6px] border border-[color-mix(in_srgb,var(--status-warn)_45%,transparent)] border-l-[3px] border-l-[var(--status-warn)] bg-[#fffbeb]/80 p-4"
              >
                <div className="flex items-start gap-2.5">
                  <AlertTriangle
                    className="mt-0.5 size-4 shrink-0 text-[var(--status-warn-text)]"
                    aria-hidden="true"
                  />
                  <div className="min-w-0 space-y-0.5">
                    <h3 className="text-sm font-semibold text-foreground">
                      {t.metrics.blindTitle}
                    </h3>
                    <p className="text-xs leading-5 text-[var(--text-secondary)]">
                      {t.metrics.blindSubtitle}
                    </p>
                  </div>
                </div>

                {/* (a) Weak attack detection */}
                {blindSpots.missedAttacks.length > 0 && (
                  <div className="space-y-2">
                    <div className="space-y-0.5">
                      <div className="text-xs font-semibold text-[var(--status-warn-text)]">
                        {interpolate(t.metrics.blindMissedAttacksTitle, {
                          threshold: formatPercentForLang(
                            thresholds.detectionThreshold * 100,
                            lang
                          ),
                        })}
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {t.metrics.blindMissedAttacksHint}
                      </p>
                    </div>
                    <ul className="space-y-1.5">
                      {blindSpots.missedAttacks.map((row) => (
                        <li
                          key={`blind-attack-${row.key}`}
                          className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 rounded-[4px] border border-[color-mix(in_srgb,var(--status-warn)_25%,transparent)] bg-card px-3 py-2 text-xs"
                        >
                          <div className="flex min-w-0 flex-wrap items-center gap-2">
                            <span className="font-medium text-foreground break-words">
                              {row.title}
                            </span>
                            <span className={WARN_TAG_CLASS}>
                              {t.metrics.blindTagWeakDetection}
                            </span>
                          </div>
                          <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-muted-foreground tabular-nums">
                            <span className="font-medium text-foreground">
                              {interpolate(t.metrics.blindMissedAttackSummary, {
                                rate: formatPercentForLang(
                                  row.ratePercent,
                                  lang
                                ),
                                missed: formatIntegerForLang(
                                  row.missedGreenCount,
                                  lang
                                ),
                                total: formatIntegerForLang(row.count, lang),
                              })}
                            </span>
                            {row.hasVerdictSplit && row.greyCount > 0 && (
                              <span>
                                ·{" "}
                                {interpolate(
                                  t.metrics.blindMissedAttackGreyExtra,
                                  {
                                    grey: formatIntegerForLang(
                                      row.greyCount,
                                      lang
                                    ),
                                  }
                                )}
                              </span>
                            )}
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* (b) Frequent false alarms on legitimate scenarios */}
                {blindSpots.falseAlarmHotspots.length > 0 && (
                  <div className="space-y-2">
                    <div className="space-y-0.5">
                      <div className="text-xs font-semibold text-[var(--status-warn-text)]">
                        {interpolate(t.metrics.blindFalseAlarmsTitle, {
                          threshold: formatPercentForLang(
                            thresholds.falseAlarmThreshold * 100,
                            lang
                          ),
                        })}
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {t.metrics.blindFalseAlarmsHint}
                      </p>
                    </div>
                    <ul className="space-y-1.5">
                      {blindSpots.falseAlarmHotspots.map((row) => (
                        <li
                          key={`blind-fp-${row.key}`}
                          className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 rounded-[4px] border border-[color-mix(in_srgb,var(--status-warn)_25%,transparent)] bg-card px-3 py-2 text-xs"
                        >
                          <div className="flex min-w-0 flex-wrap items-center gap-2">
                            <span className="font-medium text-foreground break-words">
                              {row.title}
                            </span>
                            <span className={WARN_TAG_CLASS}>
                              {t.metrics.blindTagFalseAlarm}
                            </span>
                          </div>
                          <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 tabular-nums">
                            <span className="font-medium text-foreground">
                              {interpolate(t.metrics.blindFalseAlarmSummary, {
                                rate: formatPercentForLang(
                                  row.ratePercent,
                                  lang
                                ),
                                flagged: formatIntegerForLang(
                                  row.detected,
                                  lang
                                ),
                                total: formatIntegerForLang(row.count, lang),
                              })}
                            </span>
                            {row.hasVerdictSplit && row.redCount > 0 && (
                              <span className="text-[var(--status-danger-text)]">
                                {interpolate(t.metrics.redCountShort, {
                                  count: formatIntegerForLang(
                                    row.redCount,
                                    lang
                                  ),
                                })}
                              </span>
                            )}
                            {row.hasVerdictSplit && row.yellowCount > 0 && (
                              <span className="text-[var(--status-warn-text)]">
                                {interpolate(t.metrics.yellowCountShort, {
                                  count: formatIntegerForLang(
                                    row.yellowCount,
                                    lang
                                  ),
                                })}
                              </span>
                            )}
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* (c) Legitimate kinds with >50% grey (no history) */}
                {blindSpots.noHistoryKinds.length > 0 && (
                  <div className="space-y-2">
                    <div className="space-y-0.5">
                      <div className="text-xs font-semibold text-[var(--status-warn-text)]">
                        {interpolate(t.metrics.blindNoHistoryTitle, {
                          threshold: formatPercentForLang(
                            thresholds.noHistoryGreyShareThreshold * 100,
                            lang
                          ),
                        })}
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {t.metrics.blindNoHistoryHint}
                      </p>
                    </div>
                    <ul className="space-y-1.5">
                      {blindSpots.noHistoryKinds.map((row) => (
                        <li
                          key={`blind-grey-${row.key}`}
                          className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 rounded-[4px] border border-[color-mix(in_srgb,var(--status-warn)_25%,transparent)] bg-card px-3 py-2 text-xs"
                        >
                          <div className="flex min-w-0 flex-wrap items-center gap-2">
                            <span className="font-medium text-foreground break-words">
                              {row.title}
                            </span>
                            <span className={WARN_TAG_CLASS}>
                              {t.metrics.blindTagNoHistory}
                            </span>
                          </div>
                          <span className="font-medium text-foreground tabular-nums">
                            {interpolate(t.metrics.blindNoHistorySummary, {
                              rate: formatPercentForLang(
                                row.greyShareFraction * 100,
                                lang
                              ),
                              grey: formatIntegerForLang(row.greyCount, lang),
                              total: formatIntegerForLang(row.count, lang),
                            })}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </section>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
