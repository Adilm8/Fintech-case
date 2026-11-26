"use client";

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
        "ui-notice min-w-0 space-y-1",
        isHighRisk ? "ui-notice-warn" : "ui-notice-neutral",
        className
      )}
    >
      <div className="ui-label-meta">{t.check.adviceEyebrow}</div>
      <p className="text-sm leading-5 text-foreground break-words">{text}</p>
    </div>
  );
}
