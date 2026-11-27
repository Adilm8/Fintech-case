"use client";

import { useT } from "@/i18n";
import { VERDICT_STYLES } from "@/lib/format";
import type { Verdict } from "@/lib/types";
import { cn } from "cn";

interface VerdictBadgeProps {
  verdict: Verdict;
  label?: string;
  className?: string;
}

const VERDICT_PILL_CLASSES: Record<Verdict, string> = {
  green: "ui-verdict-pill-green",
  yellow: "ui-verdict-pill-yellow",
  red: "ui-verdict-pill-red",
  grey: "ui-verdict-pill-grey",
  invalid: "ui-verdict-pill-invalid",
};

export function VerdictBadge({ verdict, label, className }: VerdictBadgeProps) {
  const { t } = useT();
  const style = VERDICT_STYLES[verdict] ?? VERDICT_STYLES.grey;
  const pillClass =
    VERDICT_PILL_CLASSES[verdict] ?? VERDICT_PILL_CLASSES.grey;
  const displayLabel = label?.trim() || t.verdicts[verdict] || t.verdicts.grey;

  return (
    <span className={cn("ui-verdict-pill", pillClass, className)}>
      <span
        aria-hidden="true"
        className={cn("ui-status-dot", style.dotClass)}
      />
      <span>{displayLabel}</span>
    </span>
  );
}
