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

export function VerdictBadge({ verdict, label, className }: VerdictBadgeProps) {
  const { t } = useT();
  const style = VERDICT_STYLES[verdict] ?? VERDICT_STYLES.grey;
  const displayLabel = label?.trim() || t.verdicts[verdict] || t.verdicts.grey;

  const textToneClass =
    verdict === "red"
      ? "text-[var(--status-danger-text)]"
      : verdict === "invalid"
        ? "text-[var(--status-invalid-text)]"
        : undefined;

  return (
    <span className={cn("ui-status", textToneClass, className)}>
      <span
        aria-hidden="true"
        className={cn("ui-status-dot", style.dotClass)}
      />
      <span>{displayLabel}</span>
    </span>
  );
}
