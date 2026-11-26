"use client";

import { useEffect, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useT, type Dictionary, type Lang } from "@/i18n";
import { ApiError, getErrorMessage, getMetrics } from "@/lib/api";
import {
  formatIntegerForLang,
  formatPercentForLang,
  localizeBackendText,
  pickDisclaimer,
  VERDICT_STYLES,
} from "@/lib/format";
import type {
  MetricsKindItem,
  MetricsResponse,
  MetricsVerdictCounts,
  Verdict,
} from "@/lib/types";
import { cn } from "cn";

interface NormalizedKindRow {
  key: string;
  title: string;
  category: "attack" | "legit" | null;
  count: number;
  detected: number;
  redCount: number;
  yellowCount: number;
  hasVerdictSplit: boolean;
  ratePercent: number | null;
  redPercent: number;
  yellowPercent: number;
  isFalsePositiveMetric: boolean;
}

interface NormalizedHistoryReplay {
  total: number | null;
  flagged: number | null;
  alertRatePercent: number | null;
  verdicts: MetricsVerdictCounts | null;
}

interface NormalizedMetrics {
  total: number | null;
  attacks: number | null;
  legit: number | null;
  detectionRatePercent: number | null;
  detectedAttacksCount: number | null;
  stoppedRedCount: number | null;
  stoppedRedRatePercent: number | null;
  escalatedYellowCount: number | null;
  escalatedYellowRatePercent: number | null;
  falseAlarmRatePercent: number | null;
  historyReplay: NormalizedHistoryReplay | null;
  byKind: NormalizedKindRow[];
  disclaimer: string | null;
  seed: number | null;
}

interface LoadState {
  nonce: number;
  lang: Lang;
  data: MetricsResponse | null;
  unavailable: boolean;
  errorMessage: string | null;
}

const CYRILLIC_RE = /[\u0400-\u04FF]/;
const KAZAKH_SPECIFIC_RE = /[әғқңөұүһіӘҒҚҢӨҰҮҺІ]/;
const RAW_SLUG_RE = /^[a-z0-9]+(?:[_-][a-z0-9]+)+$/i;

const REPLAY_VERDICT_ORDER: readonly Verdict[] = [
  "green",
  "yellow",
  "red",
  "grey",
  "invalid",
] as const;

/**
 * Converts a raw rate value into a 0..100 percentage.
 * Treats values in [0, 1] as fractions (e.g. 0.94 -> 94) and values > 1 as percentages.
 */
function toPercent(value: number | null | undefined): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return null;
  }
  const scaled = value <= 1 && value >= 0 ? value * 100 : value;
  return Math.max(0, Math.min(100, scaled));
}

function isRawIdentifier(value: string): boolean {
  const trimmed = value.trim();
  if (!trimmed) return true;
  const lower = trimmed.toLowerCase();
  if (lower === "attack" || lower === "legit") return true;
  return RAW_SLUG_RE.test(trimmed);
}

function firstValidLabel(
  candidates: Array<string | null | undefined>
): string | null {
  for (const candidate of candidates) {
    const trimmed = candidate?.trim();
    if (trimmed && !isRawIdentifier(trimmed)) {
      return trimmed;
    }
  }
  return null;
}

function resolveKindCategory(
  item: MetricsKindItem
): "attack" | "legit" | null {
  const rawCategory = item.category?.trim().toLowerCase();
  if (rawCategory === "attack" || rawCategory === "legit") {
    return rawCategory;
  }
  const rawLabel = item.label?.trim().toLowerCase();
  if (rawLabel === "attack" || rawLabel === "legit") {
    return rawLabel;
  }
  const rawKind = item.kind?.trim().toLowerCase() ?? "";
  if (rawKind.startsWith("attack")) return "attack";
  if (rawKind.startsWith("legit")) return "legit";
  if (item.detection_rate !== undefined && item.detection_rate !== null) {
    return "attack";
  }
  if (
    item.false_positive_rate !== undefined &&
    item.false_positive_rate !== null
  ) {
    return "legit";
  }
  return null;
}

function resolveKindTitle(
  item: MetricsKindItem,
  category: "attack" | "legit" | null,
  index: number,
  lang: Lang,
  t: Dictionary,
  interpolate: (
    template: string,
    vars: Record<string, string | number>
  ) => string
): string {
  const rawKind = item.kind?.trim() ?? "";
  const kindLabelsMap: Record<string, string> = t.metrics.kindLabels;
  const mappedTitle = rawKind ? kindLabelsMap[rawKind] : undefined;

  const explicitLangLabel =
    lang === "kk"
      ? firstValidLabel([
          item.label_kk,
          item.title_kk,
          item.name_kk,
          item.description_kk,
        ])
      : lang === "en"
        ? firstValidLabel([
            item.label_en,
            item.title_en,
            item.name_en,
            item.description_en,
          ])
        : firstValidLabel([
            item.label_ru,
            item.title_ru,
            item.name_ru,
            item.description_ru,
          ]);

  if (explicitLangLabel) {
    return localizeBackendText(explicitLangLabel, lang);
  }

  const genericLabel = firstValidLabel([
    item.title,
    item.name,
    item.description,
    item.label,
  ]);

  if (genericLabel) {
    if (lang === "ru") {
      return localizeBackendText(genericLabel, lang);
    }
    if (lang === "en" && !CYRILLIC_RE.test(genericLabel)) {
      return localizeBackendText(genericLabel, lang);
    }
    if (lang === "kk") {
      const ruRef = firstValidLabel([
        item.label_ru,
        item.title_ru,
        item.name_ru,
      ]);
      const looksLocalizedKk =
        KAZAKH_SPECIFIC_RE.test(genericLabel) ||
        (Boolean(ruRef) && genericLabel !== ruRef);
      if (looksLocalizedKk) {
        return localizeBackendText(genericLabel, lang);
      }
    }
  }

  if (mappedTitle) {
    return mappedTitle;
  }

  if (genericLabel) {
    return localizeBackendText(genericLabel, lang);
  }

  const fallbackTemplate =
    category === "attack"
      ? t.metrics.kindFallbackAttack
      : category === "legit"
        ? t.metrics.kindFallbackLegit
        : t.metrics.kindFallbackOther;

  return interpolate(fallbackTemplate, { index: index + 1 });
}

function normalizeKindItem(
  item: MetricsKindItem,
  index: number,
  lang: Lang,
  t: Dictionary,
  interpolate: (
    template: string,
    vars: Record<string, string | number>
  ) => string
): NormalizedKindRow {
  const rawKind = item.kind?.trim() ?? "";
  const category = resolveKindCategory(item);
  const title = resolveKindTitle(item, category, index, lang, t, interpolate);

  const count =
    typeof item.total === "number"
      ? item.total
      : typeof item.count === "number"
        ? item.count
        : 0;
  const detected =
    typeof item.flagged_count === "number"
      ? item.flagged_count
      : typeof item.detected === "number"
        ? item.detected
        : 0;

  const hasVerdictSplit =
    item.verdicts !== undefined && item.verdicts !== null;
  const redCount = typeof item.verdicts?.red === "number" ? item.verdicts.red : 0;
  const yellowCount =
    typeof item.verdicts?.yellow === "number" ? item.verdicts.yellow : 0;

  let rawRate: number | null | undefined = item.rate;
  let isFalsePositiveMetric = category === "legit";

  if (rawRate === undefined || rawRate === null) {
    if (item.detection_rate !== undefined && item.detection_rate !== null) {
      rawRate = item.detection_rate;
      isFalsePositiveMetric = false;
    } else if (
      item.false_positive_rate !== undefined &&
      item.false_positive_rate !== null
    ) {
      rawRate = item.false_positive_rate;
      isFalsePositiveMetric = true;
    } else if (count > 0) {
      rawRate = detected / count;
    }
  }

  const ratePercent = toPercent(rawRate);
  const redPercent =
    hasVerdictSplit && count > 0
      ? Math.max(0, Math.min(100, (redCount / count) * 100))
      : 0;
  const yellowPercent =
    hasVerdictSplit && count > 0
      ? Math.max(0, Math.min(100 - redPercent, (yellowCount / count) * 100))
      : 0;

  return {
    key: `${rawKind || "kind"}-${index}`,
    title,
    category,
    count,
    detected,
    redCount,
    yellowCount,
    hasVerdictSplit,
    ratePercent,
    redPercent,
    yellowPercent,
    isFalsePositiveMetric,
  };
}

function normalizeHistoryReplay(
  raw: MetricsResponse
): NormalizedHistoryReplay | null {
  const hr = raw.history_replay;
  if (!hr || typeof hr !== "object") {
    return null;
  }

  const verdicts =
    hr.verdicts && typeof hr.verdicts === "object" ? hr.verdicts : null;
  const verdictSum = verdicts
    ? (verdicts.green ?? 0) +
      (verdicts.yellow ?? 0) +
      (verdicts.red ?? 0) +
      (verdicts.grey ?? 0) +
      (verdicts.invalid ?? 0)
    : null;

  const total =
    typeof hr.total_payments === "number"
      ? hr.total_payments
      : typeof hr.total === "number"
        ? hr.total
        : typeof hr.payments_count === "number"
          ? hr.payments_count
          : typeof hr.count === "number"
            ? hr.count
            : verdictSum !== null && verdictSum > 0
              ? verdictSum
              : null;

  const flagged =
    typeof hr.flagged_count === "number"
      ? hr.flagged_count
      : typeof hr.alert_count === "number"
        ? hr.alert_count
        : typeof hr.alerts === "number"
          ? hr.alerts
          : verdicts
            ? (verdicts.red ?? 0) + (verdicts.yellow ?? 0)
            : null;

  const rawRate =
    hr.alert_rate ??
    hr.false_positive_rate ??
    (total !== null && total > 0 && flagged !== null ? flagged / total : null);

  return {
    total,
    flagged,
    alertRatePercent: toPercent(rawRate),
    verdicts,
  };
}

function normalizeMetrics(
  raw: MetricsResponse,
  lang: Lang,
  t: Dictionary,
  interpolate: (
    template: string,
    vars: Record<string, string | number>
  ) => string
): NormalizedMetrics {
  const total = raw.summary?.total_cases ?? raw.total ?? null;
  const attacks = raw.summary?.total_attack ?? raw.attacks ?? null;
  const legit = raw.summary?.total_legit ?? raw.legit ?? null;

  const detectionRatePercent = toPercent(
    raw.summary?.detection_rate ?? raw.detection_rate
  );
  const falseAlarmRatePercent = toPercent(
    raw.summary?.false_positive_rate ?? raw.false_alarm_rate
  );

  const byKind = Array.isArray(raw.by_kind)
    ? raw.by_kind.map((item, idx) =>
        normalizeKindItem(item, idx, lang, t, interpolate)
      )
    : [];

  const attackVerdicts = raw.verdict_by_label?.attack;
  const attackKindRows = byKind.filter(
    (row) => row.category === "attack" && row.hasVerdictSplit
  );

  const stoppedRedCount =
    typeof attackVerdicts?.red === "number"
      ? attackVerdicts.red
      : attackKindRows.length > 0
        ? attackKindRows.reduce((acc, row) => acc + row.redCount, 0)
        : null;

  const escalatedYellowCount =
    typeof attackVerdicts?.yellow === "number"
      ? attackVerdicts.yellow
      : attackKindRows.length > 0
        ? attackKindRows.reduce((acc, row) => acc + row.yellowCount, 0)
        : null;

  const detectedAttacksCount =
    typeof raw.confusion?.tp === "number"
      ? raw.confusion.tp
      : stoppedRedCount !== null || escalatedYellowCount !== null
        ? (stoppedRedCount ?? 0) + (escalatedYellowCount ?? 0)
        : null;

  const stoppedRedRatePercent =
    attacks !== null && attacks > 0 && stoppedRedCount !== null
      ? toPercent(stoppedRedCount / attacks)
      : null;

  const escalatedYellowRatePercent =
    attacks !== null && attacks > 0 && escalatedYellowCount !== null
      ? toPercent(escalatedYellowCount / attacks)
      : null;

  const historyReplay = normalizeHistoryReplay(raw);
  const disclaimer = pickDisclaimer(raw, lang, t.metrics.defaultDisclaimer);

  return {
    total,
    attacks,
    legit,
    detectionRatePercent,
    detectedAttacksCount,
    stoppedRedCount,
    stoppedRedRatePercent,
    escalatedYellowCount,
    escalatedYellowRatePercent,
    falseAlarmRatePercent,
    historyReplay,
    byKind,
    disclaimer,
    seed: typeof raw.seed === "number" ? raw.seed : null,
  };
}

function MetricsNeutralSkeleton() {
  return (
    <div className="space-y-4 sm:space-y-5" aria-busy="true">
      <div className="ui-page-header">
        <div className="space-y-2">
          <Skeleton className="h-6 w-40 rounded-[4px]" />
          <Skeleton className="h-4 w-72 max-w-full rounded-[4px]" />
        </div>
        <Skeleton className="h-9 w-full rounded-[6px] sm:w-28" />
      </div>

      <div className="ui-kpi-strip">
        {Array.from({ length: 4 }).map((_, idx) => (
          <div key={`init-top-skeleton-${idx}`} className="ui-kpi-cell">
            <Skeleton className="h-3.5 w-24 rounded-[4px]" />
            <Skeleton className="h-6 w-20 rounded-[4px]" />
          </div>
        ))}
      </div>

      <div className="ui-kpi-strip-3">
        {Array.from({ length: 3 }).map((_, idx) => (
          <div key={`init-mid-skeleton-${idx}`} className="ui-kpi-cell">
            <Skeleton className="h-3.5 w-32 rounded-[4px]" />
            <Skeleton className="h-6 w-24 rounded-[4px]" />
            <Skeleton className="h-3 w-28 rounded-[4px]" />
          </div>
        ))}
      </div>

      <Card>
        <CardHeader className="border-b border-border pb-3.5">
          <Skeleton className="h-5 w-52 rounded-[4px]" />
          <Skeleton className="mt-1.5 h-4 w-80 max-w-full rounded-[4px]" />
        </CardHeader>
        <CardContent className="space-y-4">
          {Array.from({ length: 4 }).map((_, idx) => (
            <div key={`init-bar-skeleton-${idx}`} className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <Skeleton className="h-4 w-48 rounded-[4px]" />
                <Skeleton className="h-4 w-20 rounded-[4px]" />
              </div>
              <Skeleton className="h-2 w-full rounded-[2px]" />
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

export default function MetricsPage() {
  const { t, lang, mounted, interpolate } = useT();
  const [retryNonce, setRetryNonce] = useState(0);
  const [loadState, setLoadState] = useState<LoadState | null>(null);

  useEffect(() => {
    if (!mounted) return;
    const controller = new AbortController();

    getMetrics(lang, { signal: controller.signal })
      .then((response) => {
        setLoadState({
          nonce: retryNonce,
          lang,
          data: response,
          unavailable: false,
          errorMessage: null,
        });
      })
      .catch((err) => {
        if (err instanceof DOMException && err.name === "AbortError") {
          return;
        }
        const isNotFoundOrNetwork =
          (err instanceof ApiError &&
            (err.status === 404 || err.isNetworkError)) ||
          !(err instanceof ApiError);
        setLoadState({
          nonce: retryNonce,
          lang,
          data: null,
          unavailable: isNotFoundOrNetwork,
          errorMessage: getErrorMessage(err),
        });
      });

    return () => {
      controller.abort();
    };
  }, [lang, mounted, retryNonce]);

  const metrics = useMemo(
    () =>
      mounted && loadState?.data
        ? normalizeMetrics(loadState.data, lang, t, interpolate)
        : null,
    [interpolate, lang, loadState, mounted, t]
  );

  // Wait until stored UI language is resolved before rendering text to prevent a RU -> KK/EN flash.
  if (!mounted) {
    return <MetricsNeutralSkeleton />;
  }

  const isLoading =
    loadState === null ||
    (loadState.nonce !== retryNonce && loadState.data === null);

  return (
    <div className="space-y-4 sm:space-y-5">
      <div className="ui-page-header">
        <div className="min-w-0">
          <h1 className="ui-page-title">{t.metrics.title}</h1>
          <p className="ui-page-subtitle">{t.metrics.subtitle}</p>
        </div>

        <Button
          type="button"
          variant="outline"
          onClick={() => setRetryNonce((n) => n + 1)}
          disabled={isLoading}
          className="min-h-10 w-full sm:min-h-9 sm:w-auto"
        >
          {isLoading && (
            <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
          )}
          <span>{t.common.refresh}</span>
        </Button>
      </div>

      {isLoading ? (
        <div className="space-y-4">
          <div className="ui-kpi-strip">
            {Array.from({ length: 4 }).map((_, idx) => (
              <div key={`metric-skeleton-${idx}`} className="ui-kpi-cell">
                <Skeleton className="h-3.5 w-24 rounded-[4px]" />
                <Skeleton className="h-6 w-20 rounded-[4px]" />
              </div>
            ))}
          </div>

          <div className="ui-kpi-strip-3">
            {Array.from({ length: 3 }).map((_, idx) => (
              <div key={`attack-skeleton-${idx}`} className="ui-kpi-cell">
                <Skeleton className="h-3.5 w-32 rounded-[4px]" />
                <Skeleton className="h-6 w-24 rounded-[4px]" />
                <Skeleton className="h-3 w-28 rounded-[4px]" />
              </div>
            ))}
          </div>

          <Card>
            <CardHeader className="border-b border-border pb-3.5">
              <Skeleton className="h-5 w-52 rounded-[4px]" />
              <Skeleton className="mt-1.5 h-4 w-80 max-w-full rounded-[4px]" />
            </CardHeader>
            <CardContent className="space-y-4">
              {Array.from({ length: 5 }).map((_, idx) => (
                <div key={`bar-skeleton-${idx}`} className="space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <Skeleton className="h-4 w-48 rounded-[4px]" />
                    <Skeleton className="h-4 w-20 rounded-[4px]" />
                  </div>
                  <Skeleton className="h-2 w-full rounded-[2px]" />
                </div>
              ))}
            </CardContent>
          </Card>

          <Skeleton className="h-12 w-full rounded-[6px]" />
        </div>
      ) : !metrics ? (
        <div className="ui-panel">
          <div className="ui-empty">
            <div className="ui-empty-title">{t.metrics.unavailableTitle}</div>
            <p className="ui-empty-desc">
              {loadState?.unavailable
                ? t.metrics.unavailableDescription
                : loadState?.errorMessage || t.metrics.unavailableDescription}
            </p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setRetryNonce((n) => n + 1)}
              className="mt-2 min-h-10 sm:min-h-8"
            >
              {t.common.retry}
            </Button>
          </div>
        </div>
      ) : (
        <>
          {/* Dataset composition & false alarm rate */}
          <div className="ui-kpi-strip">
            <div className="ui-kpi-cell">
              <span className="ui-kpi-label">{t.metrics.tiles.total}</span>
              <div className="ui-kpi-value">
                {formatIntegerForLang(metrics.total, lang)}
              </div>
            </div>

            <div className="ui-kpi-cell">
              <span className="ui-kpi-label">{t.metrics.tiles.attacks}</span>
              <div className="ui-kpi-value">
                {formatIntegerForLang(metrics.attacks, lang)}
              </div>
            </div>

            <div className="ui-kpi-cell">
              <span className="ui-kpi-label">{t.metrics.tiles.legit}</span>
              <div className="ui-kpi-value">
                {formatIntegerForLang(metrics.legit, lang)}
              </div>
            </div>

            <div className="ui-kpi-cell">
              <span className="ui-kpi-label">
                {t.metrics.tiles.falseAlarmRate}
              </span>
              <div
                className={cn(
                  "ui-kpi-value",
                  (metrics.falseAlarmRatePercent ?? 0) > 10 &&
                    "text-[var(--status-warn-text)]"
                )}
              >
                {formatPercentForLang(metrics.falseAlarmRatePercent, lang)}
              </div>
            </div>
          </div>

          {/* Attack detection breakdown: overall + stopped (red) + escalated (yellow) */}
          <div className="ui-kpi-strip-3">
            <div className="ui-kpi-cell">
              <span className="ui-kpi-label">
                {t.metrics.tiles.detectionRate}
              </span>
              <div className="ui-kpi-value text-[var(--brand-text)]">
                {formatPercentForLang(metrics.detectionRatePercent, lang)}
              </div>
              {metrics.detectedAttacksCount !== null &&
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
                )}
            </div>

            <div className="ui-kpi-cell">
              <span className="ui-kpi-label">{t.metrics.tiles.stoppedRed}</span>
              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                <span className="ui-kpi-value text-[var(--status-danger-text)]">
                  {formatIntegerForLang(metrics.stoppedRedCount, lang)}
                </span>
                {metrics.stoppedRedRatePercent !== null && (
                  <span className="text-xs font-medium tabular-nums text-[var(--status-danger-text)]">
                    ({formatPercentForLang(metrics.stoppedRedRatePercent, lang)})
                  </span>
                )}
              </div>
              {metrics.stoppedRedCount !== null && metrics.attacks !== null && (
                <div className="text-xs text-muted-foreground tabular-nums">
                  {interpolate(t.metrics.ofAttacks, {
                    count: formatIntegerForLang(metrics.stoppedRedCount, lang),
                    total: formatIntegerForLang(metrics.attacks, lang),
                  })}
                </div>
              )}
            </div>

            <div className="ui-kpi-cell">
              <span className="ui-kpi-label">
                {t.metrics.tiles.escalatedYellow}
              </span>
              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                <span className="ui-kpi-value text-[var(--status-warn-text)]">
                  {formatIntegerForLang(metrics.escalatedYellowCount, lang)}
                </span>
                {metrics.escalatedYellowRatePercent !== null && (
                  <span className="text-xs font-medium tabular-nums text-[var(--status-warn-text)]">
                    (
                    {formatPercentForLang(
                      metrics.escalatedYellowRatePercent,
                      lang
                    )}
                    )
                  </span>
                )}
              </div>
              {metrics.escalatedYellowCount !== null &&
                metrics.attacks !== null && (
                  <div className="text-xs text-muted-foreground tabular-nums">
                    {interpolate(t.metrics.ofAttacks, {
                      count: formatIntegerForLang(
                        metrics.escalatedYellowCount,
                        lang
                      ),
                      total: formatIntegerForLang(metrics.attacks, lang),
                    })}
                  </div>
                )}
            </div>
          </div>

          {/* Client 1-year history replay */}
          <Card className="min-w-0">
            <CardHeader className="border-b border-border pb-3.5">
              <CardTitle>{t.metrics.historyReplayTitle}</CardTitle>
              <CardDescription className="mt-0.5">
                {t.metrics.historyReplaySubtitle}
              </CardDescription>
            </CardHeader>

            <CardContent>
              {!metrics.historyReplay ? (
                <p className="text-sm text-muted-foreground">
                  {t.metrics.historyReplayUnavailable}
                </p>
              ) : (
                <div className="space-y-4">
                  <div className="ui-kpi-strip lg:grid-cols-2! [&>*]:border-b-0">
                    <div className="ui-kpi-cell">
                      <span className="ui-kpi-label">
                        {t.metrics.historyReplayTotal}
                      </span>
                      <div className="ui-kpi-value">
                        {formatIntegerForLang(metrics.historyReplay.total, lang)}
                      </div>
                    </div>

                    <div className="ui-kpi-cell">
                      <span className="ui-kpi-label">
                        {t.metrics.historyReplayAlertRate}
                      </span>
                      <div className="flex flex-wrap items-baseline gap-2">
                        <span
                          className={cn(
                            "ui-kpi-value",
                            (metrics.historyReplay.alertRatePercent ?? 0) > 15
                              ? "text-[var(--status-warn-text)]"
                              : "text-[var(--brand-text)]"
                          )}
                        >
                          {formatPercentForLang(
                            metrics.historyReplay.alertRatePercent,
                            lang
                          )}
                        </span>
                        {metrics.historyReplay.flagged !== null &&
                          metrics.historyReplay.total !== null && (
                            <span className="text-xs text-muted-foreground tabular-nums">
                              {interpolate(t.metrics.historyReplayFlagged, {
                                alerts: formatIntegerForLang(
                                  metrics.historyReplay.flagged,
                                  lang
                                ),
                                total: formatIntegerForLang(
                                  metrics.historyReplay.total,
                                  lang
                                ),
                              })}
                            </span>
                          )}
                      </div>
                    </div>
                  </div>

                  {metrics.historyReplay.alertRatePercent !== null && (
                    <div
                      role="progressbar"
                      aria-valuenow={Math.round(
                        metrics.historyReplay.alertRatePercent
                      )}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-label={interpolate(t.metrics.ariaBarLabel, {
                        name: t.metrics.historyReplayAlertRate,
                        rate: formatPercentForLang(
                          metrics.historyReplay.alertRatePercent,
                          lang
                        ),
                      })}
                      className="h-2 w-full overflow-hidden rounded-[2px] bg-muted"
                    >
                      <div
                        className={cn(
                          "h-full transition-all duration-300",
                          metrics.historyReplay.alertRatePercent > 15
                            ? "bg-[var(--status-warn)]"
                            : "bg-primary"
                        )}
                        style={{
                          width: `${metrics.historyReplay.alertRatePercent}%`,
                        }}
                      />
                    </div>
                  )}

                  {metrics.historyReplay.verdicts && (
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
                      {REPLAY_VERDICT_ORDER.map((v) => {
                        const count = metrics.historyReplay?.verdicts?.[v];
                        if (typeof count !== "number") return null;
                        if (count === 0 && (v === "grey" || v === "invalid")) {
                          return null;
                        }
                        const style = VERDICT_STYLES[v];
                        return (
                          <span key={v} className="ui-status">
                            <span
                              aria-hidden="true"
                              className={cn("ui-status-dot", style.dotClass)}
                            />
                            <span>{t.verdicts[v]}:</span>
                            <span className="font-semibold tabular-nums">
                              {formatIntegerForLang(count, lang)}
                            </span>
                          </span>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Accessible bar list by kind */}
          <Card className="min-w-0">
            <CardHeader className="border-b border-border pb-3.5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <CardTitle>{t.metrics.byKindTitle}</CardTitle>
                  <CardDescription className="mt-0.5">
                    {t.metrics.byKindSubtitle}
                  </CardDescription>
                </div>
                {metrics.seed !== null && (
                  <span className="ui-tag font-mono tabular-nums">
                    {interpolate(t.metrics.seedMeta, { seed: metrics.seed })}
                  </span>
                )}
              </div>
            </CardHeader>

            <CardContent>
              {metrics.byKind.length === 0 ? (
                <div className="ui-empty px-0">
                  <p className="ui-empty-desc">{t.metrics.byKindEmpty}</p>
                </div>
              ) : (
                <div className="space-y-4">
                  {metrics.byKind.map((row) => {
                    const percent = row.ratePercent ?? 0;
                    const formattedRate = formatPercentForLang(
                      row.ratePercent,
                      lang
                    );
                    const showStackedSplit =
                      row.hasVerdictSplit &&
                      row.count > 0 &&
                      row.redCount + row.yellowCount > 0;
                    const barColorClass = row.isFalsePositiveMetric
                      ? percent > 15
                        ? "bg-[var(--status-warn)]"
                        : "bg-[var(--status-neutral)]"
                      : percent >= 80
                        ? "bg-primary"
                        : percent >= 50
                          ? "bg-[var(--status-warn)]"
                          : "bg-[var(--status-danger)]";

                    return (
                      <div key={row.key} className="space-y-1.5">
                        <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                          <div className="flex min-w-0 flex-wrap items-center gap-2">
                            <span className="font-medium text-foreground break-words">
                              {row.title}
                            </span>
                            {row.category && (
                              <span className="ui-tag">
                                {row.category === "attack"
                                  ? t.metrics.labelAttack
                                  : t.metrics.labelLegit}
                              </span>
                            )}
                          </div>

                          <div className="flex shrink-0 flex-wrap items-center gap-2.5 text-xs tabular-nums">
                            {row.hasVerdictSplit && row.redCount > 0 && (
                              <span className="font-medium text-[var(--status-danger-text)]">
                                {interpolate(t.metrics.redCountShort, {
                                  count: formatIntegerForLang(
                                    row.redCount,
                                    lang
                                  ),
                                })}
                              </span>
                            )}
                            {row.hasVerdictSplit && row.yellowCount > 0 && (
                              <span className="font-medium text-[var(--status-warn-text)]">
                                {interpolate(t.metrics.yellowCountShort, {
                                  count: formatIntegerForLang(
                                    row.yellowCount,
                                    lang
                                  ),
                                })}
                              </span>
                            )}
                            <span className="text-muted-foreground">
                              {interpolate(t.metrics.detectedCount, {
                                detected: formatIntegerForLang(
                                  row.detected,
                                  lang
                                ),
                                total: formatIntegerForLang(row.count, lang),
                              })}
                            </span>
                            <span className="font-semibold text-foreground">
                              {formattedRate}
                            </span>
                          </div>
                        </div>

                        <div
                          role="progressbar"
                          aria-valuenow={Math.round(percent)}
                          aria-valuemin={0}
                          aria-valuemax={100}
                          aria-label={interpolate(t.metrics.ariaBarLabel, {
                            name: row.title,
                            rate: formattedRate,
                          })}
                          className="flex h-2 w-full overflow-hidden rounded-[2px] bg-muted"
                        >
                          {showStackedSplit ? (
                            <>
                              {row.redPercent > 0 && (
                                <div
                                  className="h-full bg-[var(--status-danger)] transition-all duration-300"
                                  style={{ width: `${row.redPercent}%` }}
                                />
                              )}
                              {row.yellowPercent > 0 && (
                                <div
                                  className="h-full bg-[var(--status-warn)] transition-all duration-300"
                                  style={{ width: `${row.yellowPercent}%` }}
                                />
                              )}
                            </>
                          ) : (
                            <div
                              className={cn(
                                "h-full transition-all duration-300",
                                barColorClass
                              )}
                              style={{ width: `${percent}%` }}
                            />
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Disclaimer footnote */}
          {metrics.disclaimer && (
            <div className="space-y-1 border-t border-border pt-3 text-xs text-muted-foreground">
              <div className="font-medium text-[var(--text-secondary)]">
                {t.metrics.disclaimerTitle}
              </div>
              <p className="leading-5 break-words">{metrics.disclaimer}</p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
