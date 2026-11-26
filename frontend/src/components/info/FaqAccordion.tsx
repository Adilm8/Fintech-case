"use client";

import { ChevronDown } from "lucide-react";
import { Badge } from "@/components/ui/badge";
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
        "divide-y divide-border overflow-hidden rounded-2xl border border-border bg-card shadow-[0_1px_2px_rgba(29,29,30,0.04)]",
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
                  "flex min-h-14 w-full cursor-pointer items-center justify-between gap-4 px-4 py-4 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring sm:px-5",
                  isOpen ? "bg-accent/40" : "hover:bg-muted/60"
                )}
              >
                <div className="min-w-0 flex-1 space-y-1">
                  <span className="block text-sm font-semibold leading-snug text-foreground sm:text-base">
                    {item.question}
                  </span>
                  <Badge
                    variant="secondary"
                    className="h-auto rounded-full px-2 py-0.5 text-[11px] font-medium text-muted-foreground"
                  >
                    {categoryLabels[item.category]}
                  </Badge>
                </div>
                <span
                  aria-hidden="true"
                  className={cn(
                    "flex size-8 shrink-0 items-center justify-center rounded-lg border border-border bg-card text-muted-foreground transition-transform duration-200 motion-reduce:transition-none",
                    isOpen &&
                      "rotate-180 border-primary/35 bg-accent text-[var(--brand-text)]"
                  )}
                >
                  <ChevronDown className="size-4" />
                </span>
              </button>
            </h3>

            <div
              id={panelId}
              role="region"
              aria-labelledby={buttonId}
              hidden={!isOpen}
              className="border-t border-border/60 bg-background/40 px-4 py-4 sm:px-5"
            >
              <p className="max-w-3xl text-sm leading-relaxed text-foreground/90">
                {item.answer}
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
