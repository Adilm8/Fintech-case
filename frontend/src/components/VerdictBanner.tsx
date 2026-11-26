"use client";

import {
  AlertTriangle,
  HelpCircle,
  ShieldAlert,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { VERDICT_META } from "@/lib/format";
import type { Verdict } from "@/lib/types";
import { cn } from "cn";

interface VerdictBannerProps {
  verdict: Verdict;
  headlineRu: string;
  className?: string;
}

const VERDICT_ICONS = {
  green: ShieldCheck,
  yellow: AlertTriangle,
  red: ShieldAlert,
  grey: HelpCircle,
  invalid: XCircle,
} as const;

export function VerdictBanner({
  verdict,
  headlineRu,
  className,
}: VerdictBannerProps) {
  const meta = VERDICT_META[verdict] ?? VERDICT_META.grey;
  const Icon = VERDICT_ICONS[verdict] ?? HelpCircle;

  return (
    <div
      role="status"
      className={cn(
        "flex items-start gap-4 rounded-xl border-2 px-5 py-4 shadow-xs",
        meta.bannerClass,
        className
      )}
    >
      <div
        className={cn(
          "flex size-11 shrink-0 items-center justify-center rounded-xl bg-white/80 shadow-xs",
          meta.iconColorClass
        )}
      >
        <Icon className="size-6" />
      </div>
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-2.5">
          <span className="text-lg font-bold tracking-tight sm:text-xl">
            {meta.labelRu}
          </span>
        </div>
        <p className="text-sm font-medium leading-relaxed opacity-90 sm:text-base">
          {headlineRu}
        </p>
      </div>
    </div>
  );
}
