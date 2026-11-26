"use client";

import { Phone } from "lucide-react";
import { useT } from "@/i18n";
import type { Verdict } from "@/lib/types";
import { cn } from "cn";

interface AdviceBoxProps {
  text: string;
  verdict?: Verdict;
  className?: string;
}

export function AdviceBox({ text, verdict, className }: AdviceBoxProps) {
  const { t } = useT();
  const isHighRisk = verdict === "red" || verdict === "invalid";

  return (
    <div
      className={cn(
        "flex min-w-0 items-start gap-3 rounded-xl border px-4 py-3.5 shadow-xs sm:gap-3.5",
        isHighRisk
          ? "border-amber-300 bg-amber-50/90 text-amber-950"
          : "border-[#00AB75]/25 bg-[#E8F8F2]/80 text-[#064A34]",
        className
      )}
    >
      <div
        className={cn(
          "flex size-9 shrink-0 items-center justify-center rounded-lg",
          isHighRisk
            ? "bg-amber-100 text-amber-800"
            : "bg-[#00AB75]/15 text-[#007D55]"
        )}
      >
        <Phone className="size-4" />
      </div>
      <div className="min-w-0 flex-1 space-y-0.5">
        <div className="text-xs font-semibold uppercase tracking-wide opacity-75">
          {t.check.adviceEyebrow}
        </div>
        <p className="text-sm font-medium leading-relaxed break-words">
          {text}
        </p>
      </div>
    </div>
  );
}
