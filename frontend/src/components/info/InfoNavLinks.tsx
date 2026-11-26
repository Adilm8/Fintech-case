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
   * "inline" renders compact pill links suitable for quick-link cards.
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
          "flex flex-col gap-2.5 rounded-2xl border border-border bg-card px-3 py-2.5 shadow-[0_1px_2px_rgba(29,29,30,0.03)] sm:flex-row sm:items-center sm:justify-between sm:px-4",
          className
        )}
      >
        <Link
          href={appHomeHref}
          className="inline-flex min-h-10 shrink-0 items-center gap-1.5 self-start rounded-xl px-2.5 py-1.5 text-sm font-medium text-[var(--brand-text)] transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:min-h-9"
        >
          <ArrowLeft aria-hidden="true" className="size-4 shrink-0" />
          <span>{info.common.backToApp}</span>
        </Link>

        <nav
          aria-label={info.common.sectionNavAria}
          className="no-scrollbar -mx-1 flex items-center gap-1 overflow-x-auto px-1 py-0.5 sm:mx-0 sm:px-0"
        >
          {visibleItems.map((item) => {
            const Icon = item.icon;
            const active =
              pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "inline-flex min-h-10 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-xl px-3 py-1.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:min-h-9",
                  active
                    ? "bg-accent font-semibold text-accent-foreground"
                    : "font-medium text-muted-foreground hover:bg-muted/80 hover:text-foreground"
                )}
              >
                <Icon
                  aria-hidden="true"
                  className={cn(
                    "size-4 shrink-0",
                    active ? "text-[var(--brand-text)]" : "text-muted-foreground"
                  )}
                />
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
          const Icon = item.icon;
          const active =
            pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "inline-flex min-h-10 items-center gap-1.5 rounded-xl border px-3 py-1.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:min-h-9",
                active
                  ? "border-primary/35 bg-accent font-semibold text-accent-foreground"
                  : "border-border bg-background font-medium text-foreground hover:bg-muted"
              )}
            >
              <Icon
                aria-hidden="true"
                className={cn(
                  "size-4 shrink-0",
                  active ? "text-[var(--brand-text)]" : "text-muted-foreground"
                )}
              />
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
        "flex items-center gap-1 border-l border-border/80 pl-2",
        className
      )}
    >
      {visibleItems.map((item) => {
        const Icon = item.icon;
        const active =
          pathname === item.href || pathname.startsWith(`${item.href}/`);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "relative inline-flex min-h-11 shrink-0 items-center gap-2 whitespace-nowrap rounded-xl px-3 py-2 text-sm transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:min-h-9 sm:py-1.5",
              active
                ? "bg-accent font-semibold text-accent-foreground"
                : "font-medium text-muted-foreground hover:bg-muted/80 hover:text-foreground"
            )}
          >
            <Icon
              aria-hidden="true"
              className={cn(
                "size-4 shrink-0",
                active ? "text-[var(--brand-text)]" : "text-muted-foreground"
              )}
            />
            <span>{info.nav[item.key]}</span>
            {active && (
              <span
                aria-hidden="true"
                className="absolute inset-x-3 -bottom-1.5 h-0.5 rounded-full bg-primary"
              />
            )}
          </Link>
        );
      })}
    </div>
  );
}
