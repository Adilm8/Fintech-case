"use client";

import { ChevronDown } from "lucide-react";
import type { InfoFaqItem } from "@/i18n/info/types";
import { cn } from "cn";

export interface FaqAccordionProps {
  items: readonly InfoFaqItem[];
  categoryLabels: Record<InfoFaqItem["category"], string>;
  openIds: ReadonlySet<string>;
  onToggle: (id: string) => void;
  className?: string;
}

export function FaqAccordion({
  items,
  categoryLabels,
  openIds,
  onToggle,
  className,
}: FaqAccordionProps) {
  return (
    <div
      className={cn(
        "ui-panel divide-y divide-border overflow-hidden",
        className
      )}
    >
      {items.map((item) => {
        const isOpen = openIds.has(item.id);
        const buttonId = `faq-trigger-${item.id}`;
        const panelId = `faq-panel-${item.id}`;

        return (
          <div key={item.id} className="min-w-0">
            <h3 className="m-0">
              <button
                id={buttonId}
                type="button"
                aria-expanded={isOpen}
                aria-controls={panelId}
                onClick={() => onToggle(item.id)}
                className={cn(
                  "flex min-h-12 w-full cursor-pointer items-center justify-between gap-4 px-4 py-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
                  isOpen ? "bg-muted/35" : "hover:bg-muted/40"
                )}
              >
                <div className="min-w-0 flex-1 space-y-0.5">
                  <span className="block text-sm font-semibold leading-5 text-foreground">
                    {item.question}
                  </span>
                  <span className="block text-xs text-muted-foreground">
                    {categoryLabels[item.category]}
                  </span>
                </div>
                <ChevronDown
                  aria-hidden="true"
                  className={cn(
                    "size-4 shrink-0 text-muted-foreground transition-transform duration-150 motion-reduce:transition-none",
                    isOpen && "rotate-180 text-foreground"
                  )}
                />
              </button>
            </h3>

            <div
              id={panelId}
              role="region"
              aria-labelledby={buttonId}
              hidden={!isOpen}
              className="border-t border-border bg-background/60 px-4 py-3.5"
            >
              <p className="max-w-3xl text-sm leading-6 text-[var(--text-secondary)]">
                {item.answer}
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
