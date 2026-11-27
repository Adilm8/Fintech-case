"use client";

import { useEffect, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useT, type Lang } from "@/i18n";
import { ApiError, getErrorMessage, getMetrics } from "@/lib/api";
import type { MetricsResponse } from "@/lib/types";
import { HistoryReplayCard } from "./_components/HistoryReplayCard";
import { KpiStrip, MetricsKpiSkeleton } from "./_components/KpiStrip";
import { ScenarioBreakdownCard } from "./_components/ScenarioBreakdownCard";
import {
  normalizeMetrics,
  type BlindSpotThresholds,
} from "./_lib/normalize";

const BLIND_SPOT_DETECTION_THRESHOLD = 0.8;
const FALSE_ALARM_HOTSPOT_THRESHOLD = 0.15;
const NO_HISTORY_GREY_SHARE_THRESHOLD = 0.5;
const DEFAULT_CHECK_LATENCY_MS = 3;

const BLIND_SPOT_THRESHOLDS: BlindSpotThresholds = {
  detectionThreshold: BLIND_SPOT_DETECTION_THRESHOLD,
  falseAlarmThreshold: FALSE_ALARM_HOTSPOT_THRESHOLD,
  noHistoryGreyShareThreshold: NO_HISTORY_GREY_SHARE_THRESHOLD,
};

interface LoadState {
  nonce: number;
  lang: Lang;
  data: MetricsResponse | null;
  unavailable: boolean;
  errorMessage: string | null;
}

function MetricsContentSkeleton() {
  return (
    <div className="space-y-4 sm:space-y-5">
      <MetricsKpiSkeleton />

      <Card>
        <CardHeader className="border-b border-border pb-3.5">
          <Skeleton className="h-5 w-56 max-w-full rounded-[4px]" />
          <Skeleton className="mt-1.5 h-4 w-80 max-w-full rounded-[4px]" />
        </CardHeader>
        <CardContent className="space-y-3.5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Skeleton className="h-4 w-36 rounded-[4px]" />
            <Skeleton className="h-4 w-48 rounded-[4px]" />
          </div>
          <Skeleton className="h-4 w-full rounded-[4px]" />
          <div className="flex flex-wrap gap-4">
            {Array.from({ length: 4 }).map((_, idx) => (
              <Skeleton
                key={`legend-skeleton-${idx}`}
                className="h-4 w-28 rounded-[4px]"
              />
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="gap-0 pb-0">
          <div className="space-y-1.5 pb-3">
            <Skeleton className="h-5 w-52 max-w-full rounded-[4px]" />
            <Skeleton className="h-4 w-80 max-w-full rounded-[4px]" />
          </div>
          <div className="-mx-(--card-spacing) flex gap-5 border-b border-border px-(--card-spacing) pb-2.5">
            <Skeleton className="h-5 w-40 rounded-[4px]" />
            <Skeleton className="h-5 w-48 rounded-[4px]" />
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {Array.from({ length: 5 }).map((_, idx) => (
            <div key={`bar-skeleton-${idx}`} className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <Skeleton className="h-4 w-48 max-w-full rounded-[4px]" />
                <Skeleton className="h-4 w-24 rounded-[4px]" />
              </div>
              <Skeleton className="h-2.5 w-full rounded-[3px]" />
            </div>
          ))}
        </CardContent>
      </Card>

      <Skeleton className="h-12 w-full rounded-[6px]" />
    </div>
  );
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

      <MetricsContentSkeleton />
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
        ? normalizeMetrics(
            loadState.data,
            lang,
            t,
            interpolate,
            BLIND_SPOT_THRESHOLDS
          )
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
        <MetricsContentSkeleton />
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
          <KpiStrip
            metrics={metrics}
            defaultCheckLatencyMs={DEFAULT_CHECK_LATENCY_MS}
            lang={lang}
            t={t}
            interpolate={interpolate}
          />

          <HistoryReplayCard
            historyReplay={metrics.historyReplay}
            lang={lang}
            t={t}
            interpolate={interpolate}
          />

          <ScenarioBreakdownCard
            byKind={metrics.byKind}
            totalAttacks={metrics.attacks}
            totalLegit={metrics.legit}
            thresholds={BLIND_SPOT_THRESHOLDS}
            lang={lang}
            t={t}
            interpolate={interpolate}
          />

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
