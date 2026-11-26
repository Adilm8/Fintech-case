"use client";

import { useInfoT } from "@/i18n/info";
import { VERDICT_STYLES } from "@/lib/format";
import type { Verdict } from "@/lib/types";
import { cn } from "cn";

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
      className="flex items-center justify-center py-1 text-muted-foreground"
    >
      <svg
        width="20"
        height="22"
        viewBox="0 0 24 26"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="shrink-0"
      >
        <path
          d="M12 2V22M12 22L6.5 16.5M12 22L17.5 16.5"
          stroke="currentColor"
          strokeWidth="1.5"
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
      className="hidden items-center justify-center px-1 text-muted-foreground lg:flex"
    >
      <svg
        width="24"
        height="18"
        viewBox="0 0 28 20"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="shrink-0"
      >
        <path
          d="M2 10H24M24 10L18.5 4.5M24 10L18.5 15.5"
          stroke="currentColor"
          strokeWidth="1.5"
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
      className="rounded-[8px] border border-border bg-background p-4"
    >
      {/* Top row: Input -> Pre-check */}
      <div className="grid grid-cols-1 items-stretch gap-3 lg:grid-cols-[1fr_auto_1fr]">
        <div className="ui-panel flex flex-col justify-between gap-2 p-4">
          <div className="flex items-baseline gap-2">
            <span className="font-mono text-xs tabular-nums text-muted-foreground">
              01
            </span>
            <div className="text-sm font-semibold text-foreground">
              {diagram.inputTitle}
            </div>
          </div>
          <ul className="list-disc space-y-1 pl-4 text-xs leading-5 text-[var(--text-secondary)]">
            {diagram.inputItems.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>

        <div className="flex items-center justify-center lg:hidden">
          <FlowArrowDown />
        </div>
        <FlowArrowRight />

        <div className="ui-panel flex flex-col justify-between gap-2 p-4">
          <div className="flex items-baseline gap-2">
            <span className="font-mono text-xs tabular-nums text-muted-foreground">
              02
            </span>
            <div className="text-sm font-semibold text-foreground">
              {diagram.precheckTitle}
            </div>
          </div>
          <p className="text-xs leading-5 text-[var(--text-secondary)]">
            {diagram.precheckDesc}
          </p>
        </div>
      </div>

      <FlowArrowDown />

      {/* Middle: Four parallel analysis layers */}
      <div className="ui-panel p-4">
        <div className="mb-3 flex items-baseline gap-2">
          <span className="font-mono text-xs tabular-nums text-muted-foreground">
            03
          </span>
          <span className="text-sm font-semibold text-foreground">
            {diagram.layersTitle}
          </span>
        </div>
        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
          {diagram.layers.map((layer, idx) => (
            <div
              key={layer.title}
              className="flex flex-col gap-1 rounded-[6px] border border-border bg-background p-3"
            >
              <div className="flex items-baseline gap-1.5">
                <span className="font-mono text-[11px] tabular-nums text-muted-foreground">
                  03.{idx + 1}
                </span>
                <span className="text-xs font-semibold text-foreground">
                  {layer.title}
                </span>
              </div>
              <p className="text-xs leading-5 text-muted-foreground">
                {layer.detail}
              </p>
            </div>
          ))}
        </div>
      </div>

      <FlowArrowDown />

      {/* Engine box */}
      <div className="ui-panel p-4">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-baseline gap-2">
            <span className="font-mono text-xs tabular-nums text-muted-foreground">
              04
            </span>
            <span className="text-sm font-semibold text-foreground">
              {diagram.engineTitle}
            </span>
          </div>
          <span className="ui-tag w-fit">{diagram.engineBadge}</span>
        </div>
        <p className="mt-1.5 text-xs leading-5 text-[var(--text-secondary)]">
          {diagram.engineDesc}
        </p>
      </div>

      <FlowArrowDown />

      {/* Output: Five verdict branches */}
      <div className="ui-panel p-4">
        <div className="mb-3 space-y-0.5">
          <div className="flex items-baseline gap-2">
            <span className="font-mono text-xs tabular-nums text-muted-foreground">
              05
            </span>
            <div className="text-sm font-semibold text-foreground">
              {diagram.outputTitle}
            </div>
          </div>
          <p className="text-xs leading-5 text-muted-foreground">
            {diagram.outputDesc}
          </p>
        </div>

        <div className="divide-y divide-border overflow-hidden rounded-[6px] border border-border lg:grid lg:grid-cols-5 lg:divide-x lg:divide-y-0">
          {VERDICT_ORDER.map((verdict) => {
            const style = VERDICT_STYLES[verdict];
            return (
              <div
                key={verdict}
                className="flex flex-col justify-between gap-1.5 bg-card px-3 py-2.5"
              >
                <span className={cn("ui-status", style.badgeClass)}>
                  <span
                    aria-hidden="true"
                    className={cn("ui-status-dot", style.dotClass)}
                  />
                  <span>{diagram.verdictLabels[verdict]}</span>
                </span>
                <div className="text-xs leading-4 text-muted-foreground">
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
