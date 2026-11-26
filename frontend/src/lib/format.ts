import type {
  CheckResult,
  MetricsResponse,
  NextAction,
  Signal,
  Verdict,
} from "./types";

export function pickHeadline(
  result: Pick<CheckResult, "headline" | "headline_ru">
): string {
  const localized = result.headline?.trim();
  return localized || result.headline_ru;
}

export function pickReason(
  signal: Pick<Signal, "reason" | "reason_ru">
): string {
  const localized = signal.reason?.trim();
  return localized || signal.reason_ru;
}

export function pickActionText(
  action: Pick<NextAction, "text" | "text_ru">
): string {
  const localized = action.text?.trim();
  return localized || action.text_ru;
}

export function pickDisclaimer(
  metrics: Pick<MetricsResponse, "disclaimer" | "disclaimer_ru">
): string | null {
  const localized = metrics.disclaimer?.trim();
  if (localized) return localized;
  const fallback = metrics.disclaimer_ru?.trim();
  return fallback || null;
}

export interface VerdictStyle {
  verdict: Verdict;
  badgeClass: string;
  bannerClass: string;
  dotClass: string;
  iconColorClass: string;
  actionButtonClass?: string;
}

export const VERDICT_STYLES: Record<Verdict, VerdictStyle> = {
  green: {
    verdict: "green",
    badgeClass: "border-[#00AB75]/30 bg-[#00AB75]/10 text-[#006B49]",
    bannerClass: "border-[#00AB75]/35 bg-[#E8F8F2] text-[#064A34]",
    dotClass: "bg-[#00AB75]",
    iconColorClass: "text-[var(--brand-text)]",
  },
  yellow: {
    verdict: "yellow",
    badgeClass: "border-amber-300/80 bg-amber-50 text-amber-900",
    bannerClass: "border-amber-300 bg-amber-50/95 text-amber-950",
    dotClass: "bg-amber-500",
    iconColorClass: "text-amber-700",
  },
  red: {
    verdict: "red",
    badgeClass: "border-red-300/80 bg-red-50 text-red-800",
    bannerClass: "border-red-300 bg-red-50/95 text-red-950",
    dotClass: "bg-red-600",
    iconColorClass: "text-red-600",
    actionButtonClass: "bg-red-600 text-white hover:bg-red-700",
  },
  grey: {
    verdict: "grey",
    badgeClass: "border-[#DCDCE2] bg-[#F0F0F5] text-[#4A4A4E]",
    bannerClass: "border-[#DCDCE2] bg-[#F0F0F5] text-[#1D1D1E]",
    dotClass: "bg-[#737376]",
    iconColorClass: "text-[#57575A]",
  },
  invalid: {
    verdict: "invalid",
    badgeClass: "border-rose-300 bg-rose-50 text-rose-950",
    bannerClass: "border-rose-400/80 bg-rose-50/95 text-rose-950",
    dotClass: "bg-rose-900",
    iconColorClass: "text-rose-900",
    actionButtonClass: "bg-rose-900 text-white hover:bg-rose-950",
  },
};
