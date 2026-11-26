"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Search, X } from "lucide-react";
import { FaqAccordion } from "@/components/info/FaqAccordion";
import { InfoPageHeader } from "@/components/info/InfoPageHeader";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useInfoT } from "@/i18n/info";
import type { InfoFaqItem } from "@/i18n/info/types";
import { cn } from "cn";

type CategoryFilter = "all" | InfoFaqItem["category"];

const CATEGORY_ORDER: readonly InfoFaqItem["category"][] = [
  "verdicts",
  "workflow",
  "features",
  "privacy",
] as const;

export default function HelpPage() {
  const { info, interpolate } = useInfoT();
  const content = info.help;

  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<CategoryFilter>("all");
  const [openIds, setOpenIds] = useState<Set<string>>(
    () => new Set(["why-yellow"])
  );

  const filteredItems = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return content.items.filter((item) => {
      if (category !== "all" && item.category !== category) {
        return false;
      }
      if (!normalized) return true;
      return (
        item.question.toLowerCase().includes(normalized) ||
        item.answer.toLowerCase().includes(normalized)
      );
    });
  }, [category, content.items, query]);

  const handleToggle = (id: string) => {
    setOpenIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleExpandAll = () => {
    setOpenIds(new Set(filteredItems.map((item) => item.id)));
  };

  const handleCollapseAll = () => {
    setOpenIds(new Set());
  };

  const handleResetFilters = () => {
    setQuery("");
    setCategory("all");
  };

  const allFilteredOpen =
    filteredItems.length > 0 &&
    filteredItems.every((item) => openIds.has(item.id));

  return (
    <div className="space-y-5">
      <InfoPageHeader
        title={content.title}
        subtitle={content.subtitle}
        badge={info.common.prototypeBadge}
      />

      {/* Search & Category Filter Controls */}
      <div className="ui-panel space-y-3 p-4">
        <div className="flex flex-col gap-2.5 sm:flex-row sm:items-center">
          <div className="relative flex-1">
            <Search
              aria-hidden="true"
              className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
            />
            <Input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={content.searchPlaceholder}
              aria-label={content.searchAriaLabel}
              className="h-10 rounded-[6px] bg-card pl-9 pr-9 sm:h-9"
            />
            {query && (
              <button
                type="button"
                onClick={() => setQuery("")}
                aria-label={content.clearSearch}
                className="absolute top-1/2 right-1.5 flex size-7 -translate-y-1/2 cursor-pointer items-center justify-center rounded-[4px] text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <X aria-hidden="true" className="size-4" />
              </button>
            )}
          </div>

          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={allFilteredOpen ? handleCollapseAll : handleExpandAll}
            disabled={filteredItems.length === 0}
            className="min-h-10 shrink-0 sm:min-h-9"
          >
            {allFilteredOpen ? content.collapseAll : content.expandAll}
          </Button>
        </div>

        <div className="flex flex-col gap-2.5 sm:flex-row sm:items-center sm:justify-between">
          <div
            role="group"
            aria-label={content.categoriesAriaLabel}
            className="flex flex-wrap items-center gap-1.5"
          >
            <button
              type="button"
              aria-pressed={category === "all"}
              onClick={() => setCategory("all")}
              className="ui-filter-chip focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {content.categoryAll}
            </button>

            {CATEGORY_ORDER.map((catKey) => {
              const isActive = category === catKey;
              return (
                <button
                  key={catKey}
                  type="button"
                  aria-pressed={isActive}
                  onClick={() => setCategory(catKey)}
                  className="ui-filter-chip focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  {content.categories[catKey]}
                </button>
              );
            })}
          </div>

          <div className="text-xs font-medium text-muted-foreground tabular-nums">
            {interpolate(content.shownCount, {
              shown: filteredItems.length,
              total: content.items.length,
            })}
          </div>
        </div>
      </div>

      {/* Accordion list */}
      <section aria-label={content.title}>
        {filteredItems.length > 0 ? (
          <FaqAccordion
            items={filteredItems}
            categoryLabels={content.categories}
            openIds={openIds}
            onToggle={handleToggle}
          />
        ) : (
          <div className="ui-panel">
            <div className="ui-empty">
              <h2 className="ui-empty-title">{content.emptyTitle}</h2>
              <p className="ui-empty-desc">{content.emptyDescription}</p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleResetFilters}
                className="mt-2 min-h-10 sm:min-h-8"
              >
                {content.resetFilters}
              </Button>
            </div>
          </div>
        )}
      </section>

      {/* Still need help */}
      <div className="ui-panel flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 space-y-0.5">
          <h2 className="ui-section-title">{content.stillNeedHelpTitle}</h2>
          <p className="max-w-2xl text-[13px] leading-5 text-muted-foreground">
            {content.stillNeedHelpDescription}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <Link
            href="/how-it-works"
            className={cn(
              buttonVariants({ variant: "outline" }),
              "min-h-10 sm:min-h-9"
            )}
          >
            {info.nav.howItWorks}
          </Link>
          <Link
            href="/support"
            className={cn(
              buttonVariants({ variant: "default" }),
              "min-h-10 sm:min-h-9"
            )}
          >
            {info.common.openSupportCta}
          </Link>
        </div>
      </div>
    </div>
  );
}
