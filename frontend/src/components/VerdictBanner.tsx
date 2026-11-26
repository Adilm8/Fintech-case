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

const NOTICE_VARIANT_CLASSES: Record<Verdict, string> = {
  green: "ui-notice-ok",
  yellow: "ui-notice-warn",
  red: "ui-notice-danger",
  grey: "ui-notice-neutral",
  invalid: "ui-notice-invalid",
};

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
  const noticeVariantClass =
    NOTICE_VARIANT_CLASSES[verdict] ?? NOTICE_VARIANT_CLASSES.grey;

  const fallbackTitle = t.verdicts[verdict] ?? t.verdicts.grey;
  const trimmedHeadline = headline?.trim() ?? "";
  const trimmedSubtitle = subtitle?.trim() ?? "";

  const title = trimmedHeadline || fallbackTitle;
  const resolvedSubtitle =
    trimmedSubtitle &&
    normalizeText(trimmedSubtitle) !== normalizeText(title)
      ? trimmedSubtitle
      : null;

  return (
    <div
      role="status"
      className={cn(
        "ui-notice flex min-w-0 items-start gap-2.5",
        noticeVariantClass,
        className
      )}
    >
      <Icon
        aria-hidden="true"
        className={cn("mt-0.5 size-4 shrink-0", style.iconColorClass)}
      />
      <div className="min-w-0 flex-1 space-y-0.5">
        <div className="text-[15px] font-semibold leading-snug text-foreground break-words">
          {title}
        </div>
        {resolvedSubtitle && (
          <p className="text-[13px] leading-5 text-muted-foreground break-words">
            {resolvedSubtitle}
          </p>
        )}
      </div>
    </div>
  );
}
