"use client";

import {
  AlertTriangle,
  HelpCircle,
  ShieldAlert,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { useT } from "@/i18n";
import type { Verdict } from "@/lib/types";
import { cn } from "cn";

interface VerdictBannerProps {
  verdict: Verdict;
  headline: string;
  subtitle?: string | null;
  score?: number | null;
  className?: string;
}

const VERDICT_ICONS = {
  green: ShieldCheck,
  yellow: AlertTriangle,
  red: ShieldAlert,
  grey: HelpCircle,
  invalid: XCircle,
} as const;

const BANNER_SURFACE_CLASSES: Record<
  Verdict,
  { container: string; icon: string; title: string; scorePill: string }
> = {
  green: {
    container:
      "ui-notice-ok border-[#A7F3D0] border-l-4 border-l-[#00AB75] bg-[#F3FBF7]",
    icon: "text-[#00875A]",
    title: "text-[#065F46]",
    scorePill: "ui-verdict-pill-green border-[#34D399]",
  },
  yellow: {
    container:
      "ui-notice-warn border-[#FCD34D] border-l-4 border-l-[#D97706] bg-[#FFFDF2]",
    icon: "text-[#92400E]",
    title: "text-[#78350F]",
    scorePill: "ui-verdict-pill-yellow border-[#F59E0B]",
  },
  red: {
    container:
      "ui-notice-danger border-[#FCA5A5] border-l-4 border-l-[#DC2626] bg-[#FFF5F5]",
    icon: "text-[#B42318]",
    title: "text-[#7F1D1D]",
    scorePill: "ui-verdict-pill-red border-[#F87171]",
  },
  grey: {
    container:
      "ui-notice-neutral border-[#D1D5DB] border-l-4 border-l-[#6B7280] bg-[#F8F9FA]",
    icon: "text-[#4B5563]",
    title: "text-foreground",
    scorePill: "ui-verdict-pill-grey border-[#D1D5DB]",
  },
  invalid: {
    container:
      "ui-notice-invalid border-[#FDA4AF] border-l-4 border-l-[#BE123C] bg-[#FFF5F7]",
    icon: "text-[#9F1239]",
    title: "text-[#881337]",
    scorePill: "ui-verdict-pill-invalid border-[#FB7185]",
  },
};

function normalizeText(value: string): string {
  return value.trim().toLowerCase().replace(/[.!\s]+$/g, "");
}

export function VerdictBanner({
  verdict,
  headline,
  subtitle,
  score,
  className,
}: VerdictBannerProps) {
  const { t, interpolate } = useT();
  const surface =
    BANNER_SURFACE_CLASSES[verdict] ?? BANNER_SURFACE_CLASSES.grey;
  const Icon = VERDICT_ICONS[verdict] ?? HelpCircle;

  const fallbackTitle = t.verdicts[verdict] ?? t.verdicts.grey;
  const trimmedHeadline = headline?.trim() ?? "";
  const trimmedSubtitle = subtitle?.trim() ?? "";

  const title = trimmedHeadline || fallbackTitle;
  const resolvedSubtitle =
    trimmedSubtitle &&
    normalizeText(trimmedSubtitle) !== normalizeText(title)
      ? trimmedSubtitle
      : null;

  const showScore =
    typeof score === "number" &&
    Number.isFinite(score) &&
    verdict !== "invalid";

  return (
    <div
      role="status"
      className={cn(
        "ui-notice flex min-w-0 flex-wrap items-center justify-between gap-3 px-4 py-3",
        surface.container,
        className
      )}
    >
      <div className="flex min-w-0 flex-1 items-start gap-2.5">
        <Icon
          aria-hidden="true"
          className={cn("mt-0.5 size-5 shrink-0", surface.icon)}
        />
        <div className="min-w-0 flex-1 space-y-0.5">
          <div
            className={cn(
              "text-base font-semibold leading-snug break-words",
              surface.title
            )}
          >
            {title}
          </div>
          {resolvedSubtitle && (
            <p className="text-[13px] leading-5 text-muted-foreground break-words">
              {resolvedSubtitle}
            </p>
          )}
        </div>
      </div>

      {showScore && (
        <span
          className={cn(
            "ui-verdict-pill shrink-0 px-3.5 py-1.5 text-sm font-bold tabular-nums sm:text-[15px]",
            surface.scorePill
          )}
        >
          {interpolate(t.check.riskScoreBadge, { score })}
        </span>
      )}
    </div>
  );
}
