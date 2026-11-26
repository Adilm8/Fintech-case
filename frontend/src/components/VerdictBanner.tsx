"use client";

import {
  AlertTriangle,
  HelpCircle,
  ShieldAlert,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { useT } from "@/i18n";
import { VERDICT_STYLES } from "@/lib/format";
import type { Verdict } from "@/lib/types";
import { cn } from "cn";

interface VerdictBannerProps {
  verdict: Verdict;
  headline: string;
  subtitle?: string | null;
  className?: string;
}

const VERDICT_ICONS = {
  green: ShieldCheck,
  yellow: AlertTriangle,
  red: ShieldAlert,
  grey: HelpCircle,
  invalid: XCircle,
} as const;

function normalizeText(value: string): string {
  return value.trim().toLowerCase().replace(/[.!\s]+$/g, "");
}

export function VerdictBanner({
  verdict,
  headline,
  subtitle,
  className,
}: VerdictBannerProps) {
  const { t } = useT();
  const style = VERDICT_STYLES[verdict] ?? VERDICT_STYLES.grey;
  const Icon = VERDICT_ICONS[verdict] ?? HelpCircle;

  const title = t.verdicts[verdict] ?? t.verdicts.grey;
  const trimmedHeadline = headline?.trim() ?? "";
  const trimmedSubtitle = subtitle?.trim() ?? "";

  const normalizedTitle = normalizeText(title);
  const resolvedSubtitle =
    trimmedHeadline && normalizeText(trimmedHeadline) !== normalizedTitle
      ? trimmedHeadline
      : trimmedSubtitle && normalizeText(trimmedSubtitle) !== normalizedTitle
        ? trimmedSubtitle
        : null;

  return (
    <div
      role="status"
      className={cn(
        "flex min-w-0 gap-3 rounded-xl border-2 px-4 py-3.5 shadow-xs sm:gap-4 sm:px-5 sm:py-4",
        resolvedSubtitle ? "items-start" : "items-center",
        style.bannerClass,
        className
      )}
    >
      <div
        className={cn(
          "flex size-10 shrink-0 items-center justify-center rounded-xl bg-white/85 shadow-xs sm:size-11",
          style.iconColorClass
        )}
      >
        <Icon className="size-5 sm:size-6" />
      </div>
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-2.5">
          <span className="text-lg font-bold tracking-tight break-words sm:text-xl">
            {title}
          </span>
        </div>
        {resolvedSubtitle && (
          <p className="text-sm font-medium leading-relaxed break-words opacity-90 sm:text-base">
            {resolvedSubtitle}
          </p>
        )}
      </div>
    </div>
  );
}
