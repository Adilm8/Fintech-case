"use client";

import { Phone } from "lucide-react";
import type { Verdict } from "@/lib/types";
import { cn } from "cn";

interface AdviceBoxProps {
  textRu: string;
  verdict?: Verdict;
  className?: string;
}

export function AdviceBox({ textRu, verdict, className }: AdviceBoxProps) {
  const isHighRisk = verdict === "red" || verdict === "invalid";

  return (
    <div
      className={cn(
        "flex min-w-0 items-start gap-3 rounded-xl border px-4 py-3.5 shadow-xs sm:gap-3.5",
        isHighRisk
          ? "border-amber-300 bg-amber-50/90 text-amber-950"
          : "border-sky-200 bg-sky-50/80 text-sky-950",
        className
      )}
    >
      <div
        className={cn(
          "flex size-9 shrink-0 items-center justify-center rounded-lg",
          isHighRisk
            ? "bg-amber-100 text-amber-800"
            : "bg-sky-100 text-sky-800"
        )}
      >
        <Phone className="size-4" />
      </div>
      <div className="min-w-0 flex-1 space-y-0.5">
        <div className="text-xs font-semibold uppercase tracking-wide opacity-75">
          Рекомендация перед подписанием
        </div>
        <p className="text-sm font-medium leading-relaxed break-words">
          {textRu}
        </p>
      </div>
    </div>
  );
}
