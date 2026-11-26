"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  FileBarChart2,
  Info,
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
import { useT, type Lang } from "@/i18n";
import { ApiError, getErrorMessage, getMetrics } from "@/lib/api";
import { pickDisclaimer } from "@/lib/format";
import type { MetricsKindItem, MetricsResponse } from "@/lib/types";
import { cn } from "cn";

interface NormalizedKindRow {
  key: string;
  title: string;
  category: "attack" | "legit" | null;
  count: number;
  detected: number;
  ratePercent: number | null;
  isFalsePositiveMetric: boolean;
}

interface NormalizedMetrics {
  total: number | null;
  attacks: number | null;
  legit: number | null;
  detectionRatePercent: number | null;
  falseAlarmRatePercent: number | null;
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

const LOCALE_BY_LANG: Record<Lang, string> = {
  ru: "ru-RU",
  kk: "kk-KZ",
  en: "en-US",
};

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

function formatPercent(value: number | null, lang: Lang): string {
  if (value === null || !Number.isFinite(value)) {
    return "—";
  }
  const hasFraction = Math.abs(value % 1) >= 0.05;
  const formatted = new Intl.NumberFormat(LOCALE_BY_LANG[lang], {
    minimumFractionDigits: hasFraction ? 1 : 0,
    maximumFractionDigits: 1,
  }).format(value);
  return `${formatted}%`;
}

function formatInteger(value: number | null, lang: Lang): string {
  if (value === null || !Number.isFinite(value)) {
    return "—";
  }
  return new Intl.NumberFormat(LOCALE_BY_LANG[lang]).format(value);
}

function humanizeKind(kind: string): string {
  const spaced = kind.replace(/[_-]+/g, " ").trim();
  if (!spaced) return kind;
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

function normalizeKindItem(
  item: MetricsKindItem,
  index: number
): NormalizedKindRow {
  const rawLabel = item.label?.trim() ?? "";
  const rawKind = item.kind?.trim() ?? "";
  const lowerLabel = rawLabel.toLowerCase();

  let category: "attack" | "legit" | null = null;
  if (lowerLabel === "attack") category = "attack";
  else if (lowerLabel === "legit") category = "legit";

  // Prefer item.label as given when it is a human-readable label (not a raw enum tag).
  const title =
    rawLabel && category === null
      ? rawLabel
      : rawKind
        ? humanizeKind(rawKind)
        : rawLabel || `#${index + 1}`;

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

  return {
    key: `${rawKind || rawLabel || "kind"}-${index}`,
    title,
    category,
    count,
    detected,
    ratePercent: toPercent(rawRate),
    isFalsePositiveMetric,
  };
}

function normalizeMetrics(raw: MetricsResponse): NormalizedMetrics {
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
    ? raw.by_kind.map((item, idx) => normalizeKindItem(item, idx))
    : [];

  const disclaimer = pickDisclaimer(raw);

  return {
    total,
    attacks,
    legit,
    detectionRatePercent,
    falseAlarmRatePercent,
    byKind,
    disclaimer,
    seed: typeof raw.seed === "number" ? raw.seed : null,
  };
}

export default function MetricsPage() {
  const { t, lang, interpolate } = useT();
  const [retryNonce, setRetryNonce] = useState(0);
  const [loadState, setLoadState] = useState<LoadState | null>(null);

  useEffect(() => {
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
  }, [lang, retryNonce]);

  const isLoading =
    loadState === null ||
    (loadState.nonce !== retryNonce && loadState.data === null);

  const metrics = useMemo(
    () => (loadState?.data ? normalizeMetrics(loadState.data) : null),
    [loadState]
  );

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
          <div className="grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-3 lg:grid-cols-5">
            {Array.from({ length: 5 }).map((_, idx) => (
              <Card key={`metric-skeleton-${idx}`} className="py-4">
                <CardContent className="space-y-3">
                  <Skeleton className="h-3.5 w-24" />
                  <Skeleton className="h-8 w-20" />
                </CardContent>
              </Card>
            ))}
          </div>

          <Card>
            <CardHeader className="border-b border-border pb-4">
              <Skeleton className="h-5 w-52" />
              <Skeleton className="mt-1.5 h-4 w-80" />
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
          {/* Summary tiles */}
          <div className="grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-3 lg:grid-cols-5">
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
                  {formatInteger(metrics.total, lang)}
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
                  {formatInteger(metrics.attacks, lang)}
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
                  {formatInteger(metrics.legit, lang)}
                </div>
              </CardContent>
            </Card>

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
                  {formatPercent(metrics.detectionRatePercent, lang)}
                </div>
              </CardContent>
            </Card>

            <Card className="col-span-2 py-4 md:col-span-1">
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
                  {formatPercent(metrics.falseAlarmRatePercent, lang)}
                </div>
              </CardContent>
            </Card>
          </div>

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
                    const formattedRate = formatPercent(row.ratePercent, lang);
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

                          <div className="flex shrink-0 items-center gap-2.5 text-xs tabular-nums">
                            <span className="text-muted-foreground">
                              {interpolate(t.metrics.detectedCount, {
                                detected: row.detected,
                                total: row.count,
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
                          className="h-2.5 w-full overflow-hidden rounded-full bg-muted"
                        >
                          <div
                            className={cn(
                              "h-full rounded-full transition-all duration-300",
                              barColorClass
                            )}
                            style={{ width: `${percent}%` }}
                          />
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
