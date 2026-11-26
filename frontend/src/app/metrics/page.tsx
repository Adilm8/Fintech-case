"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  FileBarChart2,
  History,
  Info,
  OctagonX,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
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
    <div className="space-y-5 sm:space-y-6" aria-busy="true">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-2">
          <div className="flex items-center gap-2.5">
            <Skeleton className="size-9 rounded-xl" />
            <Skeleton className="h-7 w-40" />
          </div>
          <Skeleton className="h-4 w-72 max-w-full" />
        </div>
        <Skeleton className="h-11 w-full rounded-xl sm:h-9 sm:w-28" />
      </div>

      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, idx) => (
          <Card key={`init-top-skeleton-${idx}`} className="py-4">
            <CardContent className="space-y-3">
              <Skeleton className="h-3.5 w-24" />
              <Skeleton className="h-8 w-20" />
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 sm:gap-4">
        {Array.from({ length: 3 }).map((_, idx) => (
          <Card key={`init-mid-skeleton-${idx}`} className="py-4">
            <CardContent className="space-y-3">
              <Skeleton className="h-3.5 w-32" />
              <Skeleton className="h-8 w-24" />
              <Skeleton className="h-3 w-28" />
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader className="border-b border-border pb-4">
          <Skeleton className="h-5 w-52" />
          <Skeleton className="mt-1.5 h-4 w-80 max-w-full" />
        </CardHeader>
        <CardContent className="pt-5 space-y-4">
          {Array.from({ length: 4 }).map((_, idx) => (
            <div key={`init-bar-skeleton-${idx}`} className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <Skeleton className="h-4 w-48" />
                <Skeleton className="h-4 w-20" />
              </div>
              <Skeleton className="h-3 w-full rounded-full" />
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
    <div className="space-y-5 sm:space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2.5">
            <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-accent text-[var(--brand-text)]">
              <BarChart3 className="size-5" />
            </div>
            <h1 className="text-xl font-semibold tracking-tight text-foreground sm:text-2xl">
              {t.metrics.title}
            </h1>
          </div>
          <p className="mt-1.5 text-sm text-muted-foreground">
            {t.metrics.subtitle}
          </p>
        </div>

        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => setRetryNonce((n) => n + 1)}
          disabled={isLoading}
          className="min-h-11 w-full gap-1.5 rounded-xl sm:min-h-9 sm:w-auto"
        >
          <RefreshCw className={cn("size-3.5", isLoading && "animate-spin")} />
          <span>{t.common.refresh}</span>
        </Button>
      </div>

      {isLoading ? (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
            {Array.from({ length: 4 }).map((_, idx) => (
              <Card key={`metric-skeleton-${idx}`} className="py-4">
                <CardContent className="space-y-3">
                  <Skeleton className="h-3.5 w-24" />
                  <Skeleton className="h-8 w-20" />
                </CardContent>
              </Card>
            ))}
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 sm:gap-4">
            {Array.from({ length: 3 }).map((_, idx) => (
              <Card key={`attack-skeleton-${idx}`} className="py-4">
                <CardContent className="space-y-3">
                  <Skeleton className="h-3.5 w-32" />
                  <Skeleton className="h-8 w-24" />
                  <Skeleton className="h-3 w-28" />
                </CardContent>
              </Card>
            ))}
          </div>

          <Card>
            <CardHeader className="border-b border-border pb-4">
              <Skeleton className="h-5 w-52" />
              <Skeleton className="mt-1.5 h-4 w-80 max-w-full" />
            </CardHeader>
            <CardContent className="pt-5 space-y-5">
              {Array.from({ length: 5 }).map((_, idx) => (
                <div key={`bar-skeleton-${idx}`} className="space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <Skeleton className="h-4 w-48" />
                    <Skeleton className="h-4 w-20" />
                  </div>
                  <Skeleton className="h-3 w-full rounded-full" />
                </div>
              ))}
            </CardContent>
          </Card>

          <Skeleton className="h-20 w-full rounded-2xl" />
        </div>
      ) : !metrics ? (
        <Card className="min-w-0">
          <CardContent className="flex flex-col items-center justify-center gap-3 py-16 px-6 text-center">
            <div className="flex size-12 items-center justify-center rounded-2xl bg-accent text-[var(--brand-text)]">
              <FileBarChart2 className="size-6" />
            </div>
            <div className="space-y-1">
              <div className="text-base font-semibold text-foreground">
                {t.metrics.unavailableTitle}
              </div>
              <p className="max-w-md text-sm text-muted-foreground">
                {loadState?.unavailable
                  ? t.metrics.unavailableDescription
                  : loadState?.errorMessage || t.metrics.unavailableDescription}
              </p>
            </div>
            <Button
              type="button"
              variant="outline"
              onClick={() => setRetryNonce((n) => n + 1)}
              className="mt-1 min-h-11 gap-2 rounded-xl sm:min-h-9"
            >
              <RefreshCw className="size-4" />
              <span>{t.common.retry}</span>
            </Button>
          </CardContent>
        </Card>
      ) : (
        <>
          {/* Dataset composition & false alarm rate */}
          <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
            <Card className="py-4">
              <CardContent className="flex flex-col justify-between gap-2">
                <div className="flex items-start justify-between gap-2">
                  <span className="text-xs font-medium text-muted-foreground sm:text-sm">
                    {t.metrics.tiles.total}
                  </span>
                  <div className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-muted text-foreground/75">
                    <BarChart3 className="size-4" />
                  </div>
                </div>
                <div className="text-2xl font-bold tabular-nums text-foreground sm:text-3xl">
                  {formatIntegerForLang(metrics.total, lang)}
                </div>
              </CardContent>
            </Card>

            <Card className="py-4">
              <CardContent className="flex flex-col justify-between gap-2">
                <div className="flex items-start justify-between gap-2">
                  <span className="text-xs font-medium text-muted-foreground sm:text-sm">
                    {t.metrics.tiles.attacks}
                  </span>
                  <div className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-red-50 text-red-600">
                    <ShieldAlert className="size-4" />
                  </div>
                </div>
                <div className="text-2xl font-bold tabular-nums text-foreground sm:text-3xl">
                  {formatIntegerForLang(metrics.attacks, lang)}
                </div>
              </CardContent>
            </Card>

            <Card className="py-4">
              <CardContent className="flex flex-col justify-between gap-2">
                <div className="flex items-start justify-between gap-2">
                  <span className="text-xs font-medium text-muted-foreground sm:text-sm">
                    {t.metrics.tiles.legit}
                  </span>
                  <div className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-accent text-[var(--brand-text)]">
                    <CheckCircle2 className="size-4" />
                  </div>
                </div>
                <div className="text-2xl font-bold tabular-nums text-foreground sm:text-3xl">
                  {formatIntegerForLang(metrics.legit, lang)}
                </div>
              </CardContent>
            </Card>

            <Card className="py-4">
              <CardContent className="flex flex-col justify-between gap-2">
                <div className="flex items-start justify-between gap-2">
                  <span className="text-xs font-medium text-muted-foreground sm:text-sm">
                    {t.metrics.tiles.falseAlarmRate}
                  </span>
                  <div
                    className={cn(
                      "flex size-8 shrink-0 items-center justify-center rounded-xl",
                      (metrics.falseAlarmRatePercent ?? 0) > 10
                        ? "bg-amber-50 text-amber-700"
                        : "bg-accent text-[var(--brand-text)]"
                    )}
                  >
                    <AlertTriangle className="size-4" />
                  </div>
                </div>
                <div className="text-2xl font-bold tabular-nums text-foreground sm:text-3xl">
                  {formatPercentForLang(metrics.falseAlarmRatePercent, lang)}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Attack detection breakdown: overall + stopped (red) + escalated (yellow) */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 sm:gap-4">
            <Card className="py-4">
              <CardContent className="flex flex-col justify-between gap-2">
                <div className="flex items-start justify-between gap-2">
                  <span className="text-xs font-medium text-muted-foreground sm:text-sm">
                    {t.metrics.tiles.detectionRate}
                  </span>
                  <div className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-accent text-[var(--brand-text)]">
                    <ShieldCheck className="size-4" />
                  </div>
                </div>
                <div className="text-2xl font-bold tabular-nums text-[var(--brand-text)] sm:text-3xl">
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
              </CardContent>
            </Card>

            <Card className="border-red-200/80 py-4">
              <CardContent className="flex flex-col justify-between gap-2">
                <div className="flex items-start justify-between gap-2">
                  <span className="text-xs font-medium text-red-900 sm:text-sm">
                    {t.metrics.tiles.stoppedRed}
                  </span>
                  <div className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-red-50 text-red-600">
                    <OctagonX className="size-4" />
                  </div>
                </div>
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                  <span className="text-2xl font-bold tabular-nums text-red-700 sm:text-3xl">
                    {formatIntegerForLang(metrics.stoppedRedCount, lang)}
                  </span>
                  {metrics.stoppedRedRatePercent !== null && (
                    <span className="text-sm font-semibold tabular-nums text-red-700/85">
                      ({formatPercentForLang(metrics.stoppedRedRatePercent, lang)})
                    </span>
                  )}
                </div>
                {metrics.stoppedRedCount !== null &&
                  metrics.attacks !== null && (
                    <div className="text-xs text-muted-foreground tabular-nums">
                      {interpolate(t.metrics.ofAttacks, {
                        count: formatIntegerForLang(
                          metrics.stoppedRedCount,
                          lang
                        ),
                        total: formatIntegerForLang(metrics.attacks, lang),
                      })}
                    </div>
                  )}
              </CardContent>
            </Card>

            <Card className="border-amber-200/90 py-4">
              <CardContent className="flex flex-col justify-between gap-2">
                <div className="flex items-start justify-between gap-2">
                  <span className="text-xs font-medium text-amber-950 sm:text-sm">
                    {t.metrics.tiles.escalatedYellow}
                  </span>
                  <div className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-amber-50 text-amber-700">
                    <AlertTriangle className="size-4" />
                  </div>
                </div>
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                  <span className="text-2xl font-bold tabular-nums text-amber-700 sm:text-3xl">
                    {formatIntegerForLang(metrics.escalatedYellowCount, lang)}
                  </span>
                  {metrics.escalatedYellowRatePercent !== null && (
                    <span className="text-sm font-semibold tabular-nums text-amber-800/85">
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
              </CardContent>
            </Card>
          </div>

          {/* Client 1-year history replay */}
          <Card className="min-w-0">
            <CardHeader className="border-b border-border pb-4">
              <div className="flex items-start gap-2.5">
                <div className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-muted text-foreground/75">
                  <History className="size-4" />
                </div>
                <div className="min-w-0">
                  <CardTitle className="text-base font-semibold">
                    {t.metrics.historyReplayTitle}
                  </CardTitle>
                  <CardDescription className="mt-1">
                    {t.metrics.historyReplaySubtitle}
                  </CardDescription>
                </div>
              </div>
            </CardHeader>

            <CardContent className="pt-5">
              {!metrics.historyReplay ? (
                <p className="text-sm text-muted-foreground">
                  {t.metrics.historyReplayUnavailable}
                </p>
              ) : (
                <div className="space-y-4">
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <div className="rounded-xl border border-border bg-background/80 p-3.5 space-y-1">
                      <div className="text-xs font-medium text-muted-foreground">
                        {t.metrics.historyReplayTotal}
                      </div>
                      <div className="text-2xl font-bold tabular-nums text-foreground">
                        {formatIntegerForLang(metrics.historyReplay.total, lang)}
                      </div>
                    </div>

                    <div className="rounded-xl border border-border bg-background/80 p-3.5 space-y-1">
                      <div className="text-xs font-medium text-muted-foreground">
                        {t.metrics.historyReplayAlertRate}
                      </div>
                      <div className="flex flex-wrap items-baseline gap-2">
                        <span
                          className={cn(
                            "text-2xl font-bold tabular-nums",
                            (metrics.historyReplay.alertRatePercent ?? 0) > 15
                              ? "text-amber-700"
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
                      className="h-2.5 w-full overflow-hidden rounded-full bg-muted"
                    >
                      <div
                        className={cn(
                          "h-full rounded-full transition-all duration-300",
                          metrics.historyReplay.alertRatePercent > 15
                            ? "bg-amber-500"
                            : "bg-primary"
                        )}
                        style={{
                          width: `${metrics.historyReplay.alertRatePercent}%`,
                        }}
                      />
                    </div>
                  )}

                  {metrics.historyReplay.verdicts && (
                    <div className="flex flex-wrap items-center gap-2">
                      {REPLAY_VERDICT_ORDER.map((v) => {
                        const count = metrics.historyReplay?.verdicts?.[v];
                        if (typeof count !== "number") return null;
                        if (count === 0 && (v === "grey" || v === "invalid")) {
                          return null;
                        }
                        const style = VERDICT_STYLES[v];
                        return (
                          <Badge
                            key={v}
                            variant="outline"
                            className={cn(
                              "h-auto gap-1.5 px-2.5 py-0.5 text-xs font-medium tabular-nums",
                              style.badgeClass
                            )}
                          >
                            <span
                              aria-hidden="true"
                              className={cn(
                                "size-2 rounded-full shrink-0",
                                style.dotClass
                              )}
                            />
                            <span>{t.verdicts[v]}:</span>
                            <span className="font-semibold">
                              {formatIntegerForLang(count, lang)}
                            </span>
                          </Badge>
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
            <CardHeader className="border-b border-border pb-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <CardTitle className="text-base font-semibold">
                    {t.metrics.byKindTitle}
                  </CardTitle>
                  <CardDescription className="mt-1">
                    {t.metrics.byKindSubtitle}
                  </CardDescription>
                </div>
                {metrics.seed !== null && (
                  <Badge
                    variant="outline"
                    className="h-auto font-mono text-xs text-muted-foreground"
                  >
                    {interpolate(t.metrics.seedMeta, { seed: metrics.seed })}
                  </Badge>
                )}
              </div>
            </CardHeader>

            <CardContent className="pt-5">
              {metrics.byKind.length === 0 ? (
                <p className="py-6 text-center text-sm text-muted-foreground">
                  {t.metrics.byKindEmpty}
                </p>
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
                        ? "bg-amber-500"
                        : "bg-slate-400"
                      : percent >= 80
                        ? "bg-primary"
                        : percent >= 50
                          ? "bg-amber-500"
                          : "bg-red-500";

                    return (
                      <div key={row.key} className="space-y-1.5">
                        <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                          <div className="flex min-w-0 flex-wrap items-center gap-2">
                            <span className="font-medium text-foreground break-words">
                              {row.title}
                            </span>
                            {row.category && (
                              <Badge
                                variant="outline"
                                className={cn(
                                  "h-auto px-2 py-0.5 text-[11px] font-medium",
                                  row.category === "attack"
                                    ? "border-red-200 bg-red-50 text-red-800"
                                    : "border-[#00AB75]/30 bg-[#E8F8F2] text-[#006B49]"
                                )}
                              >
                                {row.category === "attack"
                                  ? t.metrics.labelAttack
                                  : t.metrics.labelLegit}
                              </Badge>
                            )}
                          </div>

                          <div className="flex flex-wrap shrink-0 items-center gap-2 text-xs tabular-nums">
                            {row.hasVerdictSplit && row.redCount > 0 && (
                              <span className="rounded bg-red-50 px-1.5 py-0.5 font-medium text-red-700">
                                {interpolate(t.metrics.redCountShort, {
                                  count: formatIntegerForLang(
                                    row.redCount,
                                    lang
                                  ),
                                })}
                              </span>
                            )}
                            {row.hasVerdictSplit && row.yellowCount > 0 && (
                              <span className="rounded bg-amber-50 px-1.5 py-0.5 font-medium text-amber-800">
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
                          className="flex h-2.5 w-full overflow-hidden rounded-full bg-muted"
                        >
                          {showStackedSplit ? (
                            <>
                              {row.redPercent > 0 && (
                                <div
                                  className="h-full bg-red-500 transition-all duration-300"
                                  style={{ width: `${row.redPercent}%` }}
                                />
                              )}
                              {row.yellowPercent > 0 && (
                                <div
                                  className="h-full bg-amber-400 transition-all duration-300"
                                  style={{ width: `${row.yellowPercent}%` }}
                                />
                              )}
                            </>
                          ) : (
                            <div
                              className={cn(
                                "h-full rounded-full transition-all duration-300",
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

          {/* Disclaimer box */}
          {metrics.disclaimer && (
            <div className="flex items-start gap-3 rounded-2xl border border-border bg-muted/60 px-4 py-3.5 text-sm text-muted-foreground sm:px-5">
              <Info className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
              <div className="min-w-0 space-y-1">
                <div className="text-xs font-semibold uppercase tracking-wide text-foreground/80">
                  {t.metrics.disclaimerTitle}
                </div>
                <p className="leading-relaxed break-words">
                  {metrics.disclaimer}
                </p>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
