"use client";

import { Badge } from "@/components/ui/badge";
import { useT } from "@/i18n";
import { VERDICT_STYLES } from "@/lib/format";
import type { Verdict } from "@/lib/types";
import { cn } from "cn";

interface VerdictBadgeProps {
  verdict: Verdict;
  className?: string;
}

export function VerdictBadge({ verdict, className }: VerdictBadgeProps) {
  const { t } = useT();
  const style = VERDICT_STYLES[verdict] ?? VERDICT_STYLES.grey;
  const label = t.verdicts[verdict] ?? t.verdicts.grey;

  return (
    <Badge
      variant="outline"
      className={cn(
        "h-auto min-h-6 gap-1.5 px-2.5 py-0.5 text-xs font-medium",
        style.badgeClass,
        className
      )}
    >
      <span
        aria-hidden="true"
        className={cn("size-2 rounded-full shrink-0", style.dotClass)}
      />
      <span>{label}</span>
    </Badge>
  );
}
