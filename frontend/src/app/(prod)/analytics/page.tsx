"use client";

import { useEffect, useMemo, useState } from "react";
import { RefreshCw } from "lucide-react";
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
    <div className="space-y-4 sm:space-y-5">
      <div className="ui-page-header">
        <div className="min-w-0">
          <h1 className="ui-page-title">{t.metrics.title}</h1>
          <p className="ui-page-subtitle">{t.metrics.subtitle}</p>
        </div>

        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => setRetryNonce((n) => n + 1)}
          disabled={isLoading}
          className="min-h-10 w-full gap-1.5 sm:min-h-8 sm:w-auto"
        >
          <RefreshCw className={cn("size-3.5", isLoading && "animate-spin")} />
          <span>{t.common.refresh}</span>
        </Button>
      </div>

      {isLoading ? (
        <div className="space-y-4">
          <Skeleton className="h-20 w-full rounded-[8px]" />
          <Skeleton className="h-20 w-full rounded-[8px]" />
          <Skeleton className="h-64 w-full rounded-[8px]" />
        </div>
      ) : !normalized ? (
        <div className="ui-panel">
          <div className="ui-empty">
            <div className="ui-empty-title">{t.metrics.unavailableTitle}</div>
            <p className="ui-empty-desc">
              {error || t.metrics.unavailableDescription}
            </p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setRetryNonce((n) => n + 1)}
              className="mt-2 min-h-10 gap-1.5 sm:min-h-8"
            >
              <RefreshCw className="size-3.5" />
              <span>{t.common.retry}</span>
            </Button>
          </div>
        </div>
      ) : (
        <>
          <div className="ui-kpi-strip">
            <div className="ui-kpi-cell">
              <span className="ui-kpi-label">{t.metrics.tiles.total}</span>
              <span className="ui-kpi-value">
                {formatIntegerForLang(normalized.total, lang)}
              </span>
            </div>

            <div className="ui-kpi-cell">
              <span className="ui-kpi-label">{t.metrics.tiles.attacks}</span>
              <span className="ui-kpi-value">
                {formatIntegerForLang(normalized.attacks, lang)}
              </span>
            </div>

            <div className="ui-kpi-cell">
              <span className="ui-kpi-label">{t.metrics.tiles.legit}</span>
              <span className="ui-kpi-value">
                {formatIntegerForLang(normalized.legit, lang)}
              </span>
            </div>

            <div className="ui-kpi-cell">
              <span className="ui-kpi-label">
                {t.metrics.tiles.falseAlarmRate}
              </span>
              <span className="ui-kpi-value">
                {formatPercentForLang(normalized.falseAlarmRate, lang)}
              </span>
            </div>
          </div>

          <div className="ui-kpi-strip-3">
            <div className="ui-kpi-cell">
              <span className="ui-kpi-label">
                {t.metrics.tiles.detectionRate}
              </span>
              <span className="ui-kpi-value text-[var(--status-ok-text)]">
                {formatPercentForLang(normalized.detectionRate, lang)}
              </span>
              {normalized.detectedCount !== null &&
                normalized.attacks !== null && (
                  <span className="text-xs text-muted-foreground tabular-nums">
                    {interpolate(t.metrics.ofAttacks, {
                      count: formatIntegerForLang(
                        normalized.detectedCount,
                        lang
                      ),
                      total: formatIntegerForLang(normalized.attacks, lang),
                    })}
                  </span>
                )}
            </div>

            <div className="ui-kpi-cell">
              <span className="ui-kpi-label">{t.metrics.tiles.stoppedRed}</span>
              <div className="flex flex-wrap items-baseline gap-1.5">
                <span className="ui-kpi-value text-[var(--status-danger-text)]">
                  {formatIntegerForLang(normalized.stoppedRed, lang)}
                </span>
                {normalized.stoppedRedRate !== null && (
                  <span className="text-xs font-medium tabular-nums text-muted-foreground">
                    ({formatPercentForLang(normalized.stoppedRedRate, lang)})
                  </span>
                )}
              </div>
            </div>

            <div className="ui-kpi-cell">
              <span className="ui-kpi-label">
                {t.metrics.tiles.escalatedYellow}
              </span>
              <div className="flex flex-wrap items-baseline gap-1.5">
                <span className="ui-kpi-value text-[var(--status-warn-text)]">
                  {formatIntegerForLang(normalized.escalatedYellow, lang)}
                </span>
                {normalized.escalatedYellowRate !== null && (
                  <span className="text-xs font-medium tabular-nums text-muted-foreground">
                    (
                    {formatPercentForLang(
                      normalized.escalatedYellowRate,
                      lang
                    )}
                    )
                  </span>
                )}
              </div>
            </div>
          </div>

          {normalized.historyReplay && (
            <Card className="min-w-0">
              <CardHeader className="border-b border-border pb-3.5">
                <CardTitle>{t.metrics.historyReplayTitle}</CardTitle>
                <CardDescription>
                  {t.metrics.historyReplaySubtitle}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4 pt-4">
                <div className="ui-kpi-strip !grid-cols-2 [&>*]:!border-b-0">
                  <div className="ui-kpi-cell">
                    <span className="ui-kpi-label">
                      {t.metrics.historyReplayTotal}
                    </span>
                    <span className="ui-kpi-value">
                      {formatIntegerForLang(
                        normalized.historyReplay.total,
                        lang
                      )}
                    </span>
                  </div>
                  <div className="ui-kpi-cell">
                    <span className="ui-kpi-label">
                      {t.metrics.historyReplayAlertRate}
                    </span>
                    <span className="ui-kpi-value text-[var(--status-ok-text)]">
                      {formatPercentForLang(
                        normalized.historyReplay.alertRate,
                        lang
                      )}
                    </span>
                  </div>
                </div>

                {normalized.historyReplay.verdicts && (
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
                    {REPLAY_VERDICT_ORDER.map((v) => {
                      const count = normalized.historyReplay?.verdicts?.[v];
                      if (typeof count !== "number") return null;
                      const style = VERDICT_STYLES[v];
                      return (
                        <span key={v} className="ui-status tabular-nums">
                          <span
                            aria-hidden="true"
                            className={cn("ui-status-dot", style.dotClass)}
                          />
                          <span>{t.verdicts[v]}:</span>
                          <span className="font-semibold">
                            {formatIntegerForLang(count, lang)}
                          </span>
                        </span>
                      );
                    })}
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          <Card className="min-w-0">
            <CardHeader className="border-b border-border pb-3.5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <CardTitle>{t.metrics.byKindTitle}</CardTitle>
                  <CardDescription>{t.metrics.byKindSubtitle}</CardDescription>
                </div>
                {normalized.seed !== null && (
                  <span className="ui-tag font-mono tabular-nums">
                    {interpolate(t.metrics.seedMeta, { seed: normalized.seed })}
                  </span>
                )}
              </div>
            </CardHeader>
            <CardContent className="space-y-4 pt-4">
              {normalized.byKind.length === 0 ? (
                <div className="ui-empty px-0 py-4">
                  <p className="ui-empty-desc">{t.metrics.byKindEmpty}</p>
                </div>
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
                            <span className="ui-tag">
                              {row.category === "attack"
                                ? t.metrics.labelAttack
                                : t.metrics.labelLegit}
                            </span>
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
                      <div className="flex h-2 w-full overflow-hidden rounded-[2px] bg-muted">
                        {showStacked ? (
                          <>
                            {row.redPercent > 0 && (
                              <div
                                className="h-full bg-[var(--status-danger)]"
                                style={{ width: `${row.redPercent}%` }}
                              />
                            )}
                            {row.yellowPercent > 0 && (
                              <div
                                className="h-full bg-[var(--status-warn)]"
                                style={{ width: `${row.yellowPercent}%` }}
                              />
                            )}
                          </>
                        ) : (
                          <div
                            className={cn(
                              "h-full",
                              row.isLegit
                                ? "bg-[var(--status-neutral)]"
                                : "bg-primary"
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
            <div className="border-t border-border pt-3 text-xs text-muted-foreground space-y-1">
              <div className="font-medium text-foreground">
                {t.metrics.disclaimerTitle}
              </div>
              <p className="leading-relaxed break-words">
                {normalized.disclaimer}
              </p>
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
