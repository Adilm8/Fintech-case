"use client";

import {
  Building2,
  Cpu,
  FileSpreadsheet,
  History,
  ScanSearch,
  ShieldCheck,
  TrendingUp,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { useInfoT } from "@/i18n/info";
import { VERDICT_STYLES } from "@/lib/format";
import type { Verdict } from "@/lib/types";
import { cn } from "cn";

const LAYER_ICONS = [History, Building2, ScanSearch, TrendingUp] as const;

const VERDICT_ORDER: readonly Verdict[] = [
  "green",
  "yellow",
  "red",
  "grey",
  "invalid",
] as const;

function FlowArrowDown() {
  return (
    <div
      aria-hidden="true"
      className="flex items-center justify-center py-1 text-muted-foreground/70"
    >
      <svg
        width="24"
        height="26"
        viewBox="0 0 24 26"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="shrink-0"
      >
        <path
          d="M12 2V22M12 22L6.5 16.5M12 22L17.5 16.5"
          stroke="currentColor"
          strokeWidth="1.75"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
}

function FlowArrowRight() {
  return (
    <div
      aria-hidden="true"
      className="hidden items-center justify-center px-1 text-muted-foreground/70 lg:flex"
    >
      <svg
        width="28"
        height="20"
        viewBox="0 0 28 20"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="shrink-0"
      >
        <path
          d="M2 10H24M24 10L18.5 4.5M24 10L18.5 15.5"
          stroke="currentColor"
          strokeWidth="1.75"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
}

export function VerificationFlowDiagram() {
  const { info } = useInfoT();
  const { diagram } = info.howItWorks;

  return (
    <div
      role="figure"
      aria-label={info.howItWorks.diagramAriaLabel}
      className="rounded-2xl border border-border bg-background/70 p-4 sm:p-6"
    >
      {/* Top row: Input -> Pre-check */}
      <div className="grid grid-cols-1 items-stretch gap-3 lg:grid-cols-[1fr_auto_1fr]">
        <div className="flex flex-col justify-between gap-2.5 rounded-xl border border-border bg-card p-4 shadow-xs">
          <div className="flex items-center gap-2.5">
            <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-accent text-[var(--brand-text)]">
              <FileSpreadsheet aria-hidden="true" className="size-4" />
            </div>
            <div className="text-sm font-semibold text-foreground">
              {diagram.inputTitle}
            </div>
          </div>
          <ul className="space-y-1.5 text-xs leading-relaxed text-muted-foreground">
            {diagram.inputItems.map((item) => (
              <li key={item} className="flex items-start gap-2">
                <span
                  aria-hidden="true"
                  className="mt-1.5 size-1.5 shrink-0 rounded-full bg-primary"
                />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="flex items-center justify-center lg:hidden">
          <FlowArrowDown />
        </div>
        <FlowArrowRight />

        <div className="flex flex-col justify-between gap-2 rounded-xl border border-border bg-card p-4 shadow-xs">
          <div className="flex items-center gap-2.5">
            <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-accent text-[var(--brand-text)]">
              <ShieldCheck aria-hidden="true" className="size-4" />
            </div>
            <div className="text-sm font-semibold text-foreground">
              {diagram.precheckTitle}
            </div>
          </div>
          <p className="text-xs leading-relaxed text-muted-foreground">
            {diagram.precheckDesc}
          </p>
        </div>
      </div>

      <FlowArrowDown />

      {/* Middle: Four parallel analysis layers */}
      <div className="rounded-xl border border-primary/25 bg-card p-4 shadow-xs">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <span className="text-sm font-semibold text-foreground">
            {diagram.layersTitle}
          </span>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {diagram.layers.map((layer, idx) => {
            const Icon = LAYER_ICONS[idx] ?? ShieldCheck;
            return (
              <div
                key={layer.title}
                className="flex flex-col gap-1.5 rounded-xl border border-border bg-background/80 p-3"
              >
                <div className="flex items-center gap-2">
                  <div className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-accent text-[var(--brand-text)]">
                    <Icon aria-hidden="true" className="size-3.5" />
                  </div>
                  <span className="text-xs font-semibold text-foreground">
                    {layer.title}
                  </span>
                </div>
                <p className="text-xs leading-relaxed text-muted-foreground">
                  {layer.detail}
                </p>
              </div>
            );
          })}
        </div>
      </div>

      <FlowArrowDown />

      {/* Engine box */}
      <div className="rounded-xl border-2 border-primary/35 bg-[#E8F8F2]/80 p-4 text-[#064A34] shadow-xs">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2.5">
            <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <Cpu aria-hidden="true" className="size-4" />
            </div>
            <span className="text-sm font-semibold">
              {diagram.engineTitle}
            </span>
          </div>
          <Badge
            variant="outline"
            className="h-auto w-fit border-[#00AB75]/35 bg-card/90 px-2.5 py-0.5 text-xs font-medium text-[#006B49]"
          >
            {diagram.engineBadge}
          </Badge>
        </div>
        <p className="mt-2 text-xs leading-relaxed opacity-90 sm:text-sm">
          {diagram.engineDesc}
        </p>
      </div>

      <FlowArrowDown />

      {/* Output: Five verdict branches */}
      <div className="rounded-xl border border-border bg-card p-4 shadow-xs">
        <div className="mb-3 space-y-1">
          <div className="text-sm font-semibold text-foreground">
            {diagram.outputTitle}
          </div>
          <p className="text-xs leading-relaxed text-muted-foreground">
            {diagram.outputDesc}
          </p>
        </div>

        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-5">
          {VERDICT_ORDER.map((verdict) => {
            const style = VERDICT_STYLES[verdict];
            return (
              <div
                key={verdict}
                className={cn(
                  "flex flex-col justify-between gap-2 rounded-xl border px-3 py-2.5",
                  style.badgeClass
                )}
              >
                <div className="flex items-center gap-2">
                  <span
                    aria-hidden="true"
                    className={cn("size-2.5 shrink-0 rounded-full", style.dotClass)}
                  />
                  <span className="text-xs font-semibold">
                    {diagram.verdictLabels[verdict]}
                  </span>
                </div>
                <div className="text-xs font-medium opacity-90">
                  {diagram.verdictActions[verdict]}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
