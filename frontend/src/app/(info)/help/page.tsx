"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  ChevronsDownUp,
  ChevronsUpDown,
  HelpCircle,
  Search,
  X,
} from "lucide-react";
import { FaqAccordion } from "@/components/info/FaqAccordion";
import { InfoPageHeader } from "@/components/info/InfoPageHeader";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
    <div className="space-y-6 sm:space-y-8">
      <InfoPageHeader
        icon={HelpCircle}
        title={content.title}
        subtitle={content.subtitle}
        badge={info.common.prototypeBadge}
      />

      {/* Search & Category Filter Controls */}
      <Card>
        <CardContent className="space-y-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
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
                className="h-11 rounded-xl bg-background pl-9 pr-9 sm:h-10"
              />
              {query && (
                <button
                  type="button"
                  onClick={() => setQuery("")}
                  aria-label={content.clearSearch}
                  className="absolute top-1/2 right-2 flex size-7 -translate-y-1/2 cursor-pointer items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <X aria-hidden="true" className="size-4" />
                </button>
              )}
            </div>

            <div className="flex shrink-0 items-center gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={allFilteredOpen ? handleCollapseAll : handleExpandAll}
                disabled={filteredItems.length === 0}
                className="min-h-11 flex-1 gap-1.5 rounded-xl sm:min-h-10 sm:flex-initial"
              >
                {allFilteredOpen ? (
                  <>
                    <ChevronsDownUp aria-hidden="true" className="size-4" />
                    <span>{content.collapseAll}</span>
                  </>
                ) : (
                  <>
                    <ChevronsUpDown aria-hidden="true" className="size-4" />
                    <span>{content.expandAll}</span>
                  </>
                )}
              </Button>
            </div>
          </div>

          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div
              role="group"
              aria-label={content.categoriesAriaLabel}
              className="flex flex-wrap items-center gap-1.5"
            >
              <button
                type="button"
                aria-pressed={category === "all"}
                onClick={() => setCategory("all")}
                className={cn(
                  "inline-flex min-h-9 cursor-pointer items-center rounded-xl border px-3 py-1.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:text-sm",
                  category === "all"
                    ? "border-primary/35 bg-accent font-semibold text-accent-foreground"
                    : "border-border bg-background text-muted-foreground hover:bg-muted hover:text-foreground"
                )}
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
                    className={cn(
                      "inline-flex min-h-9 cursor-pointer items-center rounded-xl border px-3 py-1.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:text-sm",
                      isActive
                        ? "border-primary/35 bg-accent font-semibold text-accent-foreground"
                        : "border-border bg-background text-muted-foreground hover:bg-muted hover:text-foreground"
                    )}
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
        </CardContent>
      </Card>

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
          <Card>
            <CardContent className="flex flex-col items-center justify-center gap-3 py-12 text-center">
              <div className="flex size-12 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
                <Search aria-hidden="true" className="size-5" />
              </div>
              <div className="space-y-1">
                <h2 className="text-base font-semibold text-foreground">
                  {content.emptyTitle}
                </h2>
                <p className="max-w-md text-sm text-muted-foreground">
                  {content.emptyDescription}
                </p>
              </div>
              <Button
                type="button"
                variant="outline"
                onClick={handleResetFilters}
                className="min-h-11 rounded-xl sm:min-h-9"
              >
                {content.resetFilters}
              </Button>
            </CardContent>
          </Card>
        )}
      </section>

      {/* Still need help CTA */}
      <Card className="border-primary/25 bg-accent/45">
        <CardContent className="flex flex-col gap-4 py-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0 space-y-1">
            <h2 className="text-base font-semibold text-foreground">
              {content.stillNeedHelpTitle}
            </h2>
            <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground">
              {content.stillNeedHelpDescription}
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            <Link
              href="/how-it-works"
              className={cn(
                buttonVariants({ variant: "outline" }),
                "min-h-11 rounded-xl bg-card px-4 sm:min-h-9"
              )}
            >
              <span>{info.nav.howItWorks}</span>
            </Link>
            <Link
              href="/support"
              className={cn(
                buttonVariants({ variant: "default" }),
                "min-h-11 rounded-xl px-4 sm:min-h-9"
              )}
            >
              <span>{info.common.openSupportCta}</span>
              <ArrowRight aria-hidden="true" className="size-4" />
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
