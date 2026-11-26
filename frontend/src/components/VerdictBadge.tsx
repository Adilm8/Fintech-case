"use client";

import { Badge } from "@/components/ui/badge";
import { VERDICT_META } from "@/lib/format";
import type { Verdict } from "@/lib/types";
import { cn } from "cn";

interface VerdictBadgeProps {
  verdict: Verdict;
  className?: string;
}

export function VerdictBadge({ verdict, className }: VerdictBadgeProps) {
  const meta = VERDICT_META[verdict] ?? VERDICT_META.grey;

  return (
    <Badge
      variant="outline"
      className={cn(
        "gap-1.5 px-2.5 py-1 text-xs font-medium",
        meta.badgeClass,
        className
      )}
    >
      <span
        aria-hidden="true"
        className={cn("size-2 rounded-full shrink-0", meta.dotClass)}
      />
      <span>{meta.labelRu}</span>
    </Badge>
  );
}
