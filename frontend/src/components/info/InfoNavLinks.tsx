"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  ArrowLeft,
  BookOpen,
  FileCheck2,
  Headphones,
  HelpCircle,
  Info,
  Lock,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import { useInfoT, type InfoRouteKey } from "@/i18n/info";
import { IS_PROD } from "@/lib/mode";
import { cn } from "cn";

export interface InfoNavItemConfig {
  key: InfoRouteKey;
  href: string;
  icon: LucideIcon;
  primary: boolean;
}

export const INFO_NAV_ITEMS: readonly InfoNavItemConfig[] = [
  {
    key: "howItWorks",
    href: "/how-it-works",
    icon: BookOpen,
    primary: true,
  },
  {
    key: "help",
    href: "/help",
    icon: HelpCircle,
    primary: true,
  },
  {
    key: "security",
    href: "/security",
    icon: ShieldCheck,
    primary: true,
  },
  {
    key: "support",
    href: "/support",
    icon: Headphones,
    primary: true,
  },
  {
    key: "about",
    href: "/about",
    icon: Info,
    primary: true,
  },
  {
    key: "terms",
    href: "/terms",
    icon: FileCheck2,
    primary: false,
  },
  {
    key: "privacy",
    href: "/privacy",
    icon: Lock,
    primary: false,
  },
] as const;

export const INFO_ROUTE_PATHS: readonly string[] = INFO_NAV_ITEMS.map(
  (item) => item.href
);

export function isInfoPathname(pathname: string): boolean {
  return INFO_ROUTE_PATHS.some(
    (route) => pathname === route || pathname.startsWith(`${route}/`)
  );
}

export interface InfoNavLinksProps {
  /**
   * "header" renders links matching AppHeader/ProdHeader nav tabs (for inserting into header/menu).
   * "bar" renders a self-contained horizontal navigation bar with a back-to-app link for (info)/layout.tsx.
   * "inline" renders compact rectangular links suitable for quick-link sections.
   */
  variant?: "header" | "bar" | "inline";
  includeLegal?: boolean;
  className?: string;
}

export function InfoNavLinks({
  variant = "header",
  includeLegal = false,
  className,
}: InfoNavLinksProps) {
  const pathname = usePathname();
  const { info } = useInfoT();

  const visibleItems = includeLegal
    ? INFO_NAV_ITEMS
    : INFO_NAV_ITEMS.filter((item) => item.primary);

  const appHomeHref = IS_PROD ? "/payments" : "/";

  if (variant === "bar") {
    return (
      <div
        className={cn(
          "flex flex-col gap-2 border-b border-border sm:flex-row sm:items-center sm:justify-between sm:gap-4",
          className
        )}
      >
        <Link
          href={appHomeHref}
          className="inline-flex min-h-10 shrink-0 items-center gap-1.5 self-start rounded-[6px] text-sm font-medium text-[var(--brand-text)] transition-colors hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <ArrowLeft aria-hidden="true" className="size-4 shrink-0" />
          <span>{info.common.backToApp}</span>
        </Link>

        <nav
          aria-label={info.common.sectionNavAria}
          className="ui-tabs no-scrollbar border-b-0"
        >
          {visibleItems.map((item) => {
            const active =
              pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className="ui-tab mb-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <span>{info.nav[item.key]}</span>
              </Link>
            );
          })}
        </nav>
      </div>
    );
  }

  if (variant === "inline") {
    return (
      <nav
        aria-label={info.common.sectionNavAria}
        className={cn("flex flex-wrap gap-2", className)}
      >
        {visibleItems.map((item) => {
          const active =
            pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "inline-flex min-h-10 items-center rounded-[6px] border px-3 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:min-h-8 sm:text-xs",
                active
                  ? "border-foreground bg-muted text-foreground"
                  : "border-border bg-card text-[var(--text-secondary)] hover:bg-muted hover:text-foreground"
              )}
            >
              <span>{info.nav[item.key]}</span>
            </Link>
          );
        })}
      </nav>
    );
  }

  return (
    <div
      className={cn(
        "ui-tabs no-scrollbar border-b-0 border-l border-border pl-3",
        className
      )}
    >
      {visibleItems.map((item) => {
        const active =
          pathname === item.href || pathname.startsWith(`${item.href}/`);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className="ui-tab mb-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <span>{info.nav[item.key]}</span>
          </Link>
        );
      })}
    </div>
  );
}
