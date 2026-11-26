"use client";

import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "cn";

export interface InfoPageHeaderProps {
  icon?: LucideIcon;
  title: string;
  subtitle: string;
  badge?: string;
  actions?: ReactNode;
  className?: string;
}

export function InfoPageHeader({
  title,
  subtitle,
  badge,
  actions,
  className,
}: InfoPageHeaderProps) {
  return (
    <header
      className={cn(
        "ui-page-header border-b border-border pb-4 sm:items-start",
        className
      )}
    >
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="ui-page-title">{title}</h1>
          {badge && <span className="ui-tag">{badge}</span>}
        </div>
        <p className="ui-page-subtitle max-w-3xl">{subtitle}</p>
      </div>
      {actions && (
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {actions}
        </div>
      )}
    </header>
  );
}
