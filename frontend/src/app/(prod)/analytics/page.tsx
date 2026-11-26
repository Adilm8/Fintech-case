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
import {
  formatIntegerForLang,
  formatPercentForLang,
  localizeBackendText,
  pickDisclaimer,
  VERDICT_STYLES,
} from "@/lib/format";
import { getMetrics, getProdErrorMessage } from "@/lib/prod/api";
import { RequireRole } from "@/lib/prod/session";
import type {
  MetricsKindItem,
  MetricsResponse,
  MetricsVerdictCounts,
  Verdict,
} from "@/lib/types";
import { cn } from "cn";

const REPLAY_VERDICT_ORDER: readonly Verdict[] = [
  "green",
  "yellow",
  "red",
  "grey",
  "invalid",
] as const;

function toPercent(value: number | null | undefined): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  const scaled = value <= 1 && value >= 0 ? value * 100 : value;
  return Math.max(0, Math.min(100, scaled));
}

function resolveKindCategory(
  item: MetricsKindItem
): "attack" | "legit" | null {
  const raw = (item.category || item.label || "").trim().toLowerCase();
  if (raw === "attack" || raw === "legit") return raw;
  const kind = (item.kind || "").trim().toLowerCase();
  if (kind.startsWith("attack")) return "attack";
  if (kind.startsWith("legit")) return "legit";
  if (item.detection_rate != null) return "attack";
  if (item.false_positive_rate != null) return "legit";
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
  const kindMap: Record<string, string> = t.metrics.kindLabels;
  if (rawKind && kindMap[rawKind]) return kindMap[rawKind];

  const candidate =
    lang === "kk"
      ? item.label_kk || item.title_kk || item.name_kk
      : lang === "en"
        ? item.label_en || item.title_en || item.name_en
        : item.label_ru || item.title_ru || item.name_ru;

  if (candidate?.trim()) return localizeBackendText(candidate.trim(), lang);
  if (item.title?.trim()) return localizeBackendText(item.title.trim(), lang);

  const fallback =
    category === "attack"
      ? t.metrics.kindFallbackAttack
      : category === "legit"
        ? t.metrics.kindFallbackLegit
        : t.metrics.kindFallbackOther;
  return interpolate(fallback, { index: index + 1 });
}

function AnalyticsContent() {
  const { t, lang, interpolate } = useT();
  const [retryNonce, setRetryNonce] = useState(0);
  const fetchKey = `${lang}|${retryNonce}`;
  const [loadState, setLoadState] = useState<{
    key: string;
    data: MetricsResponse | null;
    error: string | null;
  } | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    getMetrics(lang, { signal: controller.signal })
      .then((res) => {
        setLoadState({ key: fetchKey, data: res, error: null });
      })
      .catch((err) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setLoadState({
          key: fetchKey,
          data: null,
          error: getProdErrorMessage(err),
        });
      });

    return () => controller.abort();
  }, [fetchKey, lang]);

  const data = loadState?.data ?? null;
  const error = loadState?.error ?? null;
  const isLoading = loadState === null || loadState.key !== fetchKey;

  const normalized = useMemo(() => {
    if (!data) return null;

    const total = data.summary?.total_cases ?? data.total ?? null;
    const attacks = data.summary?.total_attack ?? data.attacks ?? null;
    const legit = data.summary?.total_legit ?? data.legit ?? null;
    const detectionRate = toPercent(
      data.summary?.detection_rate ?? data.detection_rate
    );
    const falseAlarmRate = toPercent(
      data.summary?.false_positive_rate ?? data.false_alarm_rate
    );

    const byKind = (data.by_kind ?? []).map((item, idx) => {
      const category = resolveKindCategory(item);
      const count = item.total ?? item.count ?? 0;
      const detected = item.flagged_count ?? item.detected ?? 0;
      const redCount = item.verdicts?.red ?? 0;
      const yellowCount = item.verdicts?.yellow ?? 0;
      const hasVerdictSplit = Boolean(item.verdicts);
      const rawRate =
        item.rate ??
        item.detection_rate ??
        item.false_positive_rate ??
        (count > 0 ? detected / count : null);
      const ratePercent = toPercent(rawRate);
      const redPercent =
        hasVerdictSplit && count > 0
          ? Math.min(100, (redCount / count) * 100)
          : 0;
      const yellowPercent =
        hasVerdictSplit && count > 0
          ? Math.min(100 - redPercent, (yellowCount / count) * 100)
          : 0;

      return {
        key: `${item.kind || "kind"}-${idx}`,
        title: resolveKindTitle(item, category, idx, lang, t, interpolate),
        category,
        count,
        detected,
        redCount,
        yellowCount,
        hasVerdictSplit,
        ratePercent,
        redPercent,
        yellowPercent,
        isLegit: category === "legit",
      };
    });

    const attackVerdicts = data.verdict_by_label?.attack;
    const stoppedRed = attackVerdicts?.red ?? null;
    const escalatedYellow = attackVerdicts?.yellow ?? null;
    const detectedCount =
      data.confusion?.tp ??
      (stoppedRed !== null || escalatedYellow !== null
        ? (stoppedRed ?? 0) + (escalatedYellow ?? 0)
        : null);

    const hr = data.history_replay;
    const hrVerdicts: MetricsVerdictCounts | null = hr?.verdicts ?? null;
    const hrTotal =
      hr?.total_payments ?? hr?.total ?? hr?.payments_count ?? hr?.count ?? null;
    const hrFlagged =
      hr?.flagged_count ??
      hr?.alert_count ??
      hr?.alerts ??
      (hrVerdicts ? (hrVerdicts.red ?? 0) + (hrVerdicts.yellow ?? 0) : null);
    const hrAlertRate = toPercent(
      hr?.alert_rate ??
        hr?.false_positive_rate ??
        (hrTotal && hrFlagged !== null ? hrFlagged / hrTotal : null)
    );

    return {
      total,
      attacks,
      legit,
      detectionRate,
      falseAlarmRate,
      stoppedRed,
      stoppedRedRate:
        attacks && stoppedRed !== null ? toPercent(stoppedRed / attacks) : null,
      escalatedYellow,
      escalatedYellowRate:
        attacks && escalatedYellow !== null
          ? toPercent(escalatedYellow / attacks)
          : null,
      detectedCount,
      byKind,
      historyReplay: hr
        ? {
            total: hrTotal,
            flagged: hrFlagged,
            alertRate: hrAlertRate,
            verdicts: hrVerdicts,
          }
        : null,
      disclaimer: pickDisclaimer(data, lang, t.metrics.defaultDisclaimer),
      seed: typeof data.seed === "number" ? data.seed : null,
    };
  }, [data, interpolate, lang, t]);

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
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-28 w-full rounded-xl" />
            ))}
          </div>
          <Skeleton className="h-64 w-full rounded-xl" />
        </div>
      ) : !normalized ? (
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
                {error || t.metrics.unavailableDescription}
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
                <div className="text-2xl font-bold tabular-nums sm:text-3xl">
                  {formatIntegerForLang(normalized.total, lang)}
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
                <div className="text-2xl font-bold tabular-nums sm:text-3xl">
                  {formatIntegerForLang(normalized.attacks, lang)}
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
                <div className="text-2xl font-bold tabular-nums sm:text-3xl">
                  {formatIntegerForLang(normalized.legit, lang)}
                </div>
              </CardContent>
            </Card>

            <Card className="py-4">
              <CardContent className="flex flex-col justify-between gap-2">
                <div className="flex items-start justify-between gap-2">
                  <span className="text-xs font-medium text-muted-foreground sm:text-sm">
                    {t.metrics.tiles.falseAlarmRate}
                  </span>
                  <div className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-accent text-[var(--brand-text)]">
                    <AlertTriangle className="size-4" />
                  </div>
                </div>
                <div className="text-2xl font-bold tabular-nums sm:text-3xl">
                  {formatPercentForLang(normalized.falseAlarmRate, lang)}
                </div>
              </CardContent>
            </Card>
          </div>

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
                  {formatPercentForLang(normalized.detectionRate, lang)}
                </div>
                {normalized.detectedCount !== null &&
                  normalized.attacks !== null && (
                    <div className="text-xs text-muted-foreground tabular-nums">
                      {interpolate(t.metrics.ofAttacks, {
                        count: formatIntegerForLang(
                          normalized.detectedCount,
                          lang
                        ),
                        total: formatIntegerForLang(normalized.attacks, lang),
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
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className="text-2xl font-bold tabular-nums text-red-700 sm:text-3xl">
                    {formatIntegerForLang(normalized.stoppedRed, lang)}
                  </span>
                  {normalized.stoppedRedRate !== null && (
                    <span className="text-sm font-semibold tabular-nums text-red-700/85">
                      ({formatPercentForLang(normalized.stoppedRedRate, lang)})
                    </span>
                  )}
                </div>
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
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className="text-2xl font-bold tabular-nums text-amber-700 sm:text-3xl">
                    {formatIntegerForLang(normalized.escalatedYellow, lang)}
                  </span>
                  {normalized.escalatedYellowRate !== null && (
                    <span className="text-sm font-semibold tabular-nums text-amber-800/85">
                      (
                      {formatPercentForLang(
                        normalized.escalatedYellowRate,
                        lang
                      )}
                      )
                    </span>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>

          {normalized.historyReplay && (
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
              <CardContent className="space-y-4 pt-5">
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div className="rounded-xl border border-border bg-background/80 p-3.5 space-y-1">
                    <div className="text-xs font-medium text-muted-foreground">
                      {t.metrics.historyReplayTotal}
                    </div>
                    <div className="text-2xl font-bold tabular-nums">
                      {formatIntegerForLang(
                        normalized.historyReplay.total,
                        lang
                      )}
                    </div>
                  </div>
                  <div className="rounded-xl border border-border bg-background/80 p-3.5 space-y-1">
                    <div className="text-xs font-medium text-muted-foreground">
                      {t.metrics.historyReplayAlertRate}
                    </div>
                    <div className="text-2xl font-bold tabular-nums text-[var(--brand-text)]">
                      {formatPercentForLang(
                        normalized.historyReplay.alertRate,
                        lang
                      )}
                    </div>
                  </div>
                </div>

                {normalized.historyReplay.verdicts && (
                  <div className="flex flex-wrap items-center gap-2">
                    {REPLAY_VERDICT_ORDER.map((v) => {
                      const count = normalized.historyReplay?.verdicts?.[v];
                      if (typeof count !== "number") return null;
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
                              "size-2 shrink-0 rounded-full",
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
              </CardContent>
            </Card>
          )}

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
                {normalized.seed !== null && (
                  <Badge
                    variant="outline"
                    className="h-auto font-mono text-xs text-muted-foreground"
                  >
                    {interpolate(t.metrics.seedMeta, { seed: normalized.seed })}
                  </Badge>
                )}
              </div>
            </CardHeader>
            <CardContent className="space-y-4 pt-5">
              {normalized.byKind.length === 0 ? (
                <p className="py-6 text-center text-sm text-muted-foreground">
                  {t.metrics.byKindEmpty}
                </p>
              ) : (
                normalized.byKind.map((row) => {
                  const pct = row.ratePercent ?? 0;
                  const showStacked =
                    row.hasVerdictSplit &&
                    row.count > 0 &&
                    row.redCount + row.yellowCount > 0;
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
                        <div className="flex items-center gap-2 text-xs tabular-nums">
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
                            {formatPercentForLang(row.ratePercent, lang)}
                          </span>
                        </div>
                      </div>
                      <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-muted">
                        {showStacked ? (
                          <>
                            {row.redPercent > 0 && (
                              <div
                                className="h-full bg-red-500"
                                style={{ width: `${row.redPercent}%` }}
                              />
                            )}
                            {row.yellowPercent > 0 && (
                              <div
                                className="h-full bg-amber-400"
                                style={{ width: `${row.yellowPercent}%` }}
                              />
                            )}
                          </>
                        ) : (
                          <div
                            className={cn(
                              "h-full rounded-full",
                              row.isLegit ? "bg-slate-400" : "bg-primary"
                            )}
                            style={{ width: `${pct}%` }}
                          />
                        )}
                      </div>
                    </div>
                  );
                })
              )}
            </CardContent>
          </Card>

          {normalized.disclaimer && (
            <div className="flex items-start gap-3 rounded-2xl border border-border bg-muted/60 px-4 py-3.5 text-sm text-muted-foreground sm:px-5">
              <Info className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
              <div className="min-w-0 space-y-1">
                <div className="text-xs font-semibold uppercase tracking-wide text-foreground/80">
                  {t.metrics.disclaimerTitle}
                </div>
                <p className="leading-relaxed break-words">
                  {normalized.disclaimer}
                </p>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default function ProdAnalyticsPage() {
  return (
    <RequireRole roles={["analyst"]}>
      <AnalyticsContent />
    </RequireRole>
  );
}
