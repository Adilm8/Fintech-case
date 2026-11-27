"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useInfoT } from "@/i18n/info";
import { cn } from "cn";

export interface SiteFooterProps {
  /**
   * Set to true when rendered inside <main> (e.g. inside (info)/layout.tsx)
   * so the footer uses inline spacing instead of a full-bleed bottom bar.
   */
  embedded?: boolean;
  className?: string;
}

// Mirrors RULESET_VERSION in backend/app/risk/config.py
const RULESET_VERSION = "2026.11.26-r3";
const HOW_IT_WORKS_HREF = "/how-it-works";

export function SiteFooter({ embedded = false, className }: SiteFooterProps) {
  const pathname = usePathname();
  const { info, appT, interpolate } = useInfoT();
  const isHowItWorksActive =
    pathname === HOW_IT_WORKS_HREF ||
    pathname.startsWith(`${HOW_IT_WORKS_HREF}/`);

  return (
    <footer
      className={cn(
        embedded
          ? "border-t border-border pt-4 text-xs text-muted-foreground"
          : "mt-auto border-t border-border bg-background text-xs text-muted-foreground",
        className
      )}
    >
      <div
        className={cn(
          "flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5",
          !embedded && "mx-auto w-full max-w-[1248px] px-4 py-3 sm:px-6"
        )}
      >
        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
          <span>{info.footer.syntheticNote}</span>
          <span aria-hidden="true" className="text-border">
            ·
          </span>
          <span className="font-mono text-[11px] tabular-nums whitespace-nowrap">
            {interpolate(appT.check.rulesetVersion, {
              version: RULESET_VERSION,
            })}
          </span>
        </div>

        <Link
          href={HOW_IT_WORKS_HREF}
          aria-current={isHowItWorksActive ? "page" : undefined}
          className={cn(
            "inline-flex min-h-8 shrink-0 items-center rounded-[4px] text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            isHowItWorksActive
              ? "font-medium text-foreground"
              : "font-medium text-[var(--brand-text)] hover:underline"
          )}
        >
          {info.nav.howItWorks}
        </Link>
      </div>
    </footer>
  );
}
