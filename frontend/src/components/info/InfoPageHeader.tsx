"use client";

import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "cn";

export interface InfoPageHeaderProps {
  icon: LucideIcon;
  title: string;
  subtitle: string;
  badge?: string;
  actions?: ReactNode;
  className?: string;
}

export function InfoPageHeader({
  icon: Icon,
  title,
  subtitle,
  badge,
  actions,
  className,
}: InfoPageHeaderProps) {
  return (
    <header
      className={cn(
        "flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between",
        className
      )}
    >
      <div className="min-w-0 space-y-2">
        <div className="flex flex-wrap items-center gap-2.5">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-accent text-[var(--brand-text)]">
            <Icon aria-hidden="true" className="size-5" />
          </div>
          <h1 className="text-xl font-semibold tracking-tight text-foreground sm:text-2xl lg:text-[1.75rem]">
            {title}
          </h1>
          {badge && (
            <Badge
              variant="secondary"
              className="h-auto rounded-full border border-border bg-card px-2.5 py-0.5 text-xs font-medium text-muted-foreground"
            >
              {badge}
            </Badge>
          )}
        </div>
        <p className="max-w-3xl text-sm leading-relaxed text-muted-foreground sm:text-base">
          {subtitle}
        </p>
      </div>
      {actions && (
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {actions}
        </div>
      )}
    </header>
  );
}
