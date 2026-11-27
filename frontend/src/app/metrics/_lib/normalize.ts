import type { Dictionary, Lang } from "@/i18n";
import { localizeBackendText, pickDisclaimer } from "@/lib/format";
import type {
  MetricsKindItem,
  MetricsResponse,
  MetricsSummary,
  MetricsVerdictCounts,
  Verdict,
} from "@/lib/types";

export interface ExtendedMetricsSummary extends MetricsSummary {
  stopped_count?: number;
  escalated_count?: number;
  stopped_rate?: number;
  escalated_rate?: number;
  legit_stopped_count?: number;
  legit_escalated_count?: number;
  avg_check_ms?: number;
  check_latency_ms?: number;
}

export interface ExtendedMetricsKindItem extends MetricsKindItem {
  stopped_count?: number;
  escalated_count?: number;
}

export interface ExtendedMetricsResponse
  extends Omit<MetricsResponse, "summary" | "by_kind"> {
  summary?: ExtendedMetricsSummary;
  by_kind?: ExtendedMetricsKindItem[];
}

export interface BlindSpotThresholds {
  detectionThreshold: number;
  falseAlarmThreshold: number;
  noHistoryGreyShareThreshold: number;
}

export interface StackedSegment {
  verdict: Verdict;
  count: number;
  rawPercent: number;
  visualWidthPercent: number;
}

export interface NormalizedKindRow {
  key: string;
  rawKind: string;
  title: string;
  category: "attack" | "legit" | null;
  count: number;
  detected: number;
  verdicts: MetricsVerdictCounts | null;
  greenCount: number;
  greyCount: number;
  yellowCount: number;
  redCount: number;
  invalidCount: number;
  hasVerdictSplit: boolean;
  ratePercent: number | null;
  detectionFraction: number | null;
  falsePositiveFraction: number | null;
  greyShareFraction: number;
  missedGreenCount: number;
  isFalsePositiveMetric: boolean;
  isAttackBlindSpot: boolean;
  isFalseAlarmHotspot: boolean;
  isNoHistoryKind: boolean;
}

export interface NormalizedHistoryReplay {
  total: number | null;
  flagged: number | null;
  alertRatePercent: number | null;
  verdicts: MetricsVerdictCounts | null;
}

export interface NormalizedMetrics {
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
  checkLatencyMs: number | null;
  historyReplay: NormalizedHistoryReplay | null;
  byKind: NormalizedKindRow[];
  disclaimer: string | null;
  seed: number | null;
}

export interface BlindSpotsSummary {
  missedAttacks: NormalizedKindRow[];
  falseAlarmHotspots: NormalizedKindRow[];
  noHistoryKinds: NormalizedKindRow[];
  totalCount: number;
}

export type InterpolateFn = (
  template: string,
  vars: Record<string, string | number>
) => string;

export const HISTORY_VERDICT_ORDER: readonly Verdict[] = [
  "green",
  "grey",
  "yellow",
  "red",
  "invalid",
] as const;

export const LEGIT_VERDICT_ORDER: readonly Verdict[] = [
  "green",
  "grey",
  "yellow",
  "red",
  "invalid",
] as const;

export const ATTACK_VERDICT_ORDER: readonly Verdict[] = [
  "red",
  "yellow",
  "grey",
  "green",
  "invalid",
] as const;

export const CORE_VERDICTS: readonly Verdict[] = [
  "green",
  "grey",
  "yellow",
  "red",
] as const;

export const VERDICT_BAR_BG: Record<Verdict, string> = {
  green: "bg-[var(--status-ok)]",
  grey: "bg-[var(--status-neutral)]",
  yellow: "bg-[var(--status-warn)]",
  red: "bg-[var(--status-danger)]",
  invalid: "bg-[var(--status-invalid)]",
};

export const WARN_TAG_CLASS =
  "ui-tag border-[color-mix(in_srgb,var(--status-warn)_40%,transparent)] bg-[#fffbeb] text-[var(--status-warn-text)]";

const CYRILLIC_RE = /[\u0400-\u04FF]/;
const KAZAKH_SPECIFIC_RE = /[әғқңөұүһіӘҒҚҢӨҰҮҺІ]/;
const RAW_SLUG_RE = /^[a-z0-9]+(?:[_-][a-z0-9]+)+$/i;

/**
 * Converts a raw rate value into a 0..100 percentage.
 * Treats values in [0, 1] as fractions (e.g. 0.87 -> 87) and values > 1 as percentages.
 */
export function toPercent(value: number | null | undefined): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return null;
  }
  const scaled = value <= 1 && value >= 0 ? value * 100 : value;
  return Math.max(0, Math.min(100, scaled));
}

function toFraction(value: number | null | undefined): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return null;
  }
  const normalized = value > 1 ? value / 100 : value;
  return Math.max(0, Math.min(1, normalized));
}

function readVerdictCount(
  verdicts: MetricsVerdictCounts | null | undefined,
  verdict: Verdict
): number {
  const val = verdicts?.[verdict];
  return typeof val === "number" && Number.isFinite(val) && val > 0 ? val : 0;
}

/**
 * Computes stacked bar segments with a minimum visible width for tiny non-zero values
 * while keeping the sum of visual widths at 100% and preserving exact raw percentages.
 */
export function computeStackedSegments(
  verdicts: MetricsVerdictCounts | null,
  order: readonly Verdict[],
  fallbackTotal?: number | null,
  minVisualPercent = 1.5
): { total: number; segments: StackedSegment[] } {
  if (!verdicts) {
    return { total: fallbackTotal ?? 0, segments: [] };
  }

  const nonZero = order
    .map((verdict) => ({
      verdict,
      count: readVerdictCount(verdicts, verdict),
    }))
    .filter((item) => item.count > 0);

  const verdictSum = nonZero.reduce((acc, item) => acc + item.count, 0);
  const total = verdictSum > 0 ? verdictSum : (fallbackTotal ?? 0);

  if (total <= 0 || nonZero.length === 0) {
    return { total, segments: [] };
  }

  const withRaw = nonZero.map((item) => ({
    ...item,
    rawPercent: (item.count / total) * 100,
  }));

  if (withRaw.length === 1) {
    return {
      total,
      segments: [
        {
          verdict: withRaw[0].verdict,
          count: withRaw[0].count,
          rawPercent: withRaw[0].rawPercent,
          visualWidthPercent: 100,
        },
      ],
    };
  }

  const effectiveMin = Math.min(minVisualPercent, 100 / withRaw.length);
  let deficit = 0;
  let reduciblePool = 0;

  for (const item of withRaw) {
    if (item.rawPercent < effectiveMin) {
      deficit += effectiveMin - item.rawPercent;
    } else {
      reduciblePool += item.rawPercent - effectiveMin;
    }
  }

  const segments: StackedSegment[] = withRaw.map((item) => {
    let visualWidthPercent: number;
    if (item.rawPercent < effectiveMin) {
      visualWidthPercent = effectiveMin;
    } else if (deficit > 0 && reduciblePool > 0) {
      const share = (item.rawPercent - effectiveMin) / reduciblePool;
      visualWidthPercent = item.rawPercent - deficit * share;
    } else {
      visualWidthPercent = item.rawPercent;
    }
    return {
      verdict: item.verdict,
      count: item.count,
      rawPercent: item.rawPercent,
      visualWidthPercent,
    };
  });

  return { total, segments };
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
  item: ExtendedMetricsKindItem
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
  item: ExtendedMetricsKindItem,
  category: "attack" | "legit" | null,
  index: number,
  lang: Lang,
  t: Dictionary,
  interpolate: InterpolateFn
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
  item: ExtendedMetricsKindItem,
  index: number,
  lang: Lang,
  t: Dictionary,
  interpolate: InterpolateFn,
  thresholds: BlindSpotThresholds
): NormalizedKindRow {
  const rawKind = item.kind?.trim() ?? "";
  const category = resolveKindCategory(item);
  const title = resolveKindTitle(item, category, index, lang, t, interpolate);

  const hasVerdictSplit =
    item.verdicts !== undefined && item.verdicts !== null;
  const verdicts = hasVerdictSplit ? (item.verdicts ?? null) : null;

  const greenCount = readVerdictCount(verdicts, "green");
  const greyCount = readVerdictCount(verdicts, "grey");
  const yellowCount = hasVerdictSplit
    ? readVerdictCount(verdicts, "yellow")
    : typeof item.escalated_count === "number" &&
        Number.isFinite(item.escalated_count)
      ? Math.max(0, item.escalated_count)
      : 0;
  const redCount = hasVerdictSplit
    ? readVerdictCount(verdicts, "red")
    : typeof item.stopped_count === "number" &&
        Number.isFinite(item.stopped_count)
      ? Math.max(0, item.stopped_count)
      : 0;
  const invalidCount = readVerdictCount(verdicts, "invalid");

  const verdictSum =
    greenCount + greyCount + yellowCount + redCount + invalidCount;
  const count =
    typeof item.total === "number"
      ? item.total
      : typeof item.count === "number"
        ? item.count
        : verdictSum;

  const detected =
    typeof item.flagged_count === "number"
      ? item.flagged_count
      : typeof item.detected === "number"
        ? item.detected
        : typeof item.stopped_count === "number" ||
            typeof item.escalated_count === "number"
          ? (item.stopped_count ?? 0) + (item.escalated_count ?? 0)
          : hasVerdictSplit
            ? redCount + yellowCount
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

  const ratePercent = toPercent(rawRate);
  const detectionFraction =
    category === "attack"
      ? (toFraction(item.detection_rate) ??
        toFraction(item.rate) ??
        (count > 0 ? detected / count : null))
      : null;

  const falsePositiveFraction =
    category === "legit"
      ? (toFraction(item.false_positive_rate) ??
        toFraction(item.rate) ??
        (count > 0 ? detected / count : null))
      : null;

  const greyDenominator = verdictSum > 0 ? verdictSum : count;
  const greyShareFraction =
    hasVerdictSplit && greyDenominator > 0 ? greyCount / greyDenominator : 0;

  const missedGreenCount = hasVerdictSplit
    ? greenCount
    : Math.max(0, count - detected);

  const isAttackBlindSpot =
    category === "attack" &&
    detectionFraction !== null &&
    detectionFraction < thresholds.detectionThreshold;

  const isFalseAlarmHotspot =
    category === "legit" &&
    falsePositiveFraction !== null &&
    falsePositiveFraction > thresholds.falseAlarmThreshold;

  const isNoHistoryKind =
    category === "legit" &&
    hasVerdictSplit &&
    greyDenominator > 0 &&
    greyShareFraction > thresholds.noHistoryGreyShareThreshold;

  return {
    key: `${rawKind || "kind"}-${index}`,
    rawKind,
    title,
    category,
    count,
    detected,
    verdicts,
    greenCount,
    greyCount,
    yellowCount,
    redCount,
    invalidCount,
    hasVerdictSplit,
    ratePercent,
    detectionFraction,
    falsePositiveFraction,
    greyShareFraction,
    missedGreenCount,
    isFalsePositiveMetric,
    isAttackBlindSpot,
    isFalseAlarmHotspot,
    isNoHistoryKind,
  };
}

function normalizeHistoryReplay(
  raw: ExtendedMetricsResponse
): NormalizedHistoryReplay | null {
  const hr = raw.history_replay;
  if (!hr || typeof hr !== "object") {
    return null;
  }

  const verdicts =
    hr.verdicts && typeof hr.verdicts === "object" ? hr.verdicts : null;
  const verdictSum = verdicts
    ? readVerdictCount(verdicts, "green") +
      readVerdictCount(verdicts, "yellow") +
      readVerdictCount(verdicts, "red") +
      readVerdictCount(verdicts, "grey") +
      readVerdictCount(verdicts, "invalid")
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
            ? readVerdictCount(verdicts, "red") +
              readVerdictCount(verdicts, "yellow")
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

export function normalizeMetrics(
  raw: MetricsResponse,
  lang: Lang,
  t: Dictionary,
  interpolate: InterpolateFn,
  thresholds: BlindSpotThresholds
): NormalizedMetrics {
  const ext: ExtendedMetricsResponse = raw;
  const total = ext.summary?.total_cases ?? ext.total ?? null;
  const attacks = ext.summary?.total_attack ?? ext.attacks ?? null;
  const legit = ext.summary?.total_legit ?? ext.legit ?? null;

  const detectionRatePercent = toPercent(
    ext.summary?.detection_rate ?? ext.detection_rate
  );
  const falseAlarmRatePercent = toPercent(
    ext.summary?.false_positive_rate ?? ext.false_alarm_rate
  );

  const byKind = Array.isArray(ext.by_kind)
    ? ext.by_kind.map((item, idx) =>
        normalizeKindItem(item, idx, lang, t, interpolate, thresholds)
      )
    : [];

  const attackVerdicts = ext.verdict_by_label?.attack;
  const attackKindRows = byKind.filter(
    (row) => row.category === "attack" && row.hasVerdictSplit
  );

  const stoppedRedCount =
    typeof ext.summary?.stopped_count === "number"
      ? ext.summary.stopped_count
      : typeof attackVerdicts?.red === "number"
        ? attackVerdicts.red
        : attackKindRows.length > 0
          ? attackKindRows.reduce((acc, row) => acc + row.redCount, 0)
          : null;

  const escalatedYellowCount =
    typeof ext.summary?.escalated_count === "number"
      ? ext.summary.escalated_count
      : typeof attackVerdicts?.yellow === "number"
        ? attackVerdicts.yellow
        : attackKindRows.length > 0
          ? attackKindRows.reduce((acc, row) => acc + row.yellowCount, 0)
          : null;

  const detectedAttacksCount =
    typeof ext.confusion?.tp === "number"
      ? ext.confusion.tp
      : stoppedRedCount !== null || escalatedYellowCount !== null
        ? (stoppedRedCount ?? 0) + (escalatedYellowCount ?? 0)
        : null;

  const stoppedRedRatePercent =
    toPercent(ext.summary?.stopped_rate) ??
    (attacks !== null && attacks > 0 && stoppedRedCount !== null
      ? toPercent(stoppedRedCount / attacks)
      : null);

  const escalatedYellowRatePercent =
    toPercent(ext.summary?.escalated_rate) ??
    (attacks !== null && attacks > 0 && escalatedYellowCount !== null
      ? toPercent(escalatedYellowCount / attacks)
      : null);

  const rawLatency =
    typeof ext.summary?.avg_check_ms === "number" &&
    Number.isFinite(ext.summary.avg_check_ms) &&
    ext.summary.avg_check_ms >= 0
      ? ext.summary.avg_check_ms
      : typeof ext.summary?.check_latency_ms === "number" &&
          Number.isFinite(ext.summary.check_latency_ms) &&
          ext.summary.check_latency_ms >= 0
        ? ext.summary.check_latency_ms
        : null;
  const checkLatencyMs = rawLatency !== null ? Math.round(rawLatency) : null;

  const historyReplay = normalizeHistoryReplay(ext);
  const disclaimer = pickDisclaimer(ext, lang, t.metrics.defaultDisclaimer);

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
    checkLatencyMs,
    historyReplay,
    byKind,
    disclaimer,
    seed: typeof ext.seed === "number" ? ext.seed : null,
  };
}

export function collectBlindSpots(rows: NormalizedKindRow[]): BlindSpotsSummary {
  const missedAttacks = rows.filter((row) => row.isAttackBlindSpot);
  const falseAlarmHotspots = rows.filter((row) => row.isFalseAlarmHotspot);
  const noHistoryKinds = rows.filter((row) => row.isNoHistoryKind);

  return {
    missedAttacks,
    falseAlarmHotspots,
    noHistoryKinds,
    totalCount:
      missedAttacks.length + falseAlarmHotspots.length + noHistoryKinds.length,
  };
}
