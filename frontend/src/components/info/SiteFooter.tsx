"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BadgeCheck, Info } from "lucide-react";
import { Separator } from "@/components/ui/separator";
import { useInfoT, type InfoRouteKey } from "@/i18n/info";
import { IS_PROD } from "@/lib/mode";
import { cn } from "cn";

export interface SiteFooterProps {
  /**
   * Set to true when rendered inside <main> (e.g. inside (info)/layout.tsx)
   * so the footer renders as a rounded card instead of a full-bleed bar.
   */
  embedded?: boolean;
  className?: string;
}

const PRODUCT_LINKS: readonly { key: InfoRouteKey; href: string }[] = [
  { key: "howItWorks", href: "/how-it-works" },
  { key: "security", href: "/security" },
  { key: "about", href: "/about" },
];

const SUPPORT_LINKS: readonly { key: InfoRouteKey; href: string }[] = [
  { key: "help", href: "/help" },
  { key: "support", href: "/support" },
];

const LEGAL_LINKS: readonly { key: InfoRouteKey; href: string }[] = [
  { key: "terms", href: "/terms" },
  { key: "privacy", href: "/privacy" },
];

export function SiteFooter({ embedded = false, className }: SiteFooterProps) {
  const pathname = usePathname();
  const { info, appT } = useInfoT();
  const appHomeHref = IS_PROD ? "/payments" : "/";

  const linkClass = (href: string) => {
    const active = pathname === href || pathname.startsWith(`${href}/`);
    return cn(
      "inline-flex min-h-8 items-center rounded-md text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
      active
        ? "font-semibold text-[var(--brand-text)]"
        : "text-muted-foreground hover:text-foreground"
    );
  };

  return (
    <footer
      className={cn(
        embedded
          ? "rounded-2xl border border-border bg-card shadow-[0_1px_2px_rgba(29,29,30,0.04)]"
          : "mt-auto border-t border-border bg-card",
        className
      )}
    >
      <div
        className={cn(
          embedded
            ? "px-5 py-6 sm:px-6 sm:py-7"
            : "mx-auto w-full max-w-[1248px] px-4 py-8 sm:px-6"
        )}
      >
        <div className="grid grid-cols-1 gap-8 md:grid-cols-12">
          <div className="space-y-3 md:col-span-5">
            <Link
              href={appHomeHref}
              className="inline-flex items-center gap-2.5 rounded-lg transition-opacity hover:opacity-85 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-[0_2px_8px_rgba(0,171,117,0.24)]">
                <BadgeCheck aria-hidden="true" className="size-5" />
              </div>
              <div className="min-w-0">
                <div className="text-sm font-semibold tracking-tight text-foreground sm:text-base">
                  {appT.brand.name}
                </div>
                <div className="text-xs text-muted-foreground">
                  {appT.brand.subtitle}
                </div>
              </div>
            </Link>
            <p className="max-w-md text-sm leading-relaxed text-muted-foreground">
              {info.footer.brandDescription}
            </p>
          </div>

          <nav
            aria-label={info.common.footerNavAria}
            className="grid grid-cols-2 gap-6 sm:grid-cols-3 md:col-span-7"
          >
            <div className="space-y-2.5">
              <h2 className="text-xs font-semibold uppercase tracking-wide text-foreground">
                {info.footer.productGroupTitle}
              </h2>
              <ul className="space-y-1">
                <li>
                  <Link href={appHomeHref} className={linkClass(appHomeHref)}>
                    {info.footer.backToPayments}
                  </Link>
                </li>
                {PRODUCT_LINKS.map((item) => (
                  <li key={item.href}>
                    <Link href={item.href} className={linkClass(item.href)}>
                      {info.nav[item.key]}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>

            <div className="space-y-2.5">
              <h2 className="text-xs font-semibold uppercase tracking-wide text-foreground">
                {info.footer.supportGroupTitle}
              </h2>
              <ul className="space-y-1">
                {SUPPORT_LINKS.map((item) => (
                  <li key={item.href}>
                    <Link href={item.href} className={linkClass(item.href)}>
                      {info.nav[item.key]}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>

            <div className="col-span-2 space-y-2.5 sm:col-span-1">
              <h2 className="text-xs font-semibold uppercase tracking-wide text-foreground">
                {info.footer.legalGroupTitle}
              </h2>
              <ul className="space-y-1">
                {LEGAL_LINKS.map((item) => (
                  <li key={item.href}>
                    <Link href={item.href} className={linkClass(item.href)}>
                      {info.nav[item.key]}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          </nav>
        </div>

        <Separator className="my-5" />

        <div className="flex flex-col gap-2.5 rounded-xl border border-amber-300/70 bg-amber-50/80 px-3.5 py-3 text-amber-950 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-2.5 sm:items-center">
            <Info
              aria-hidden="true"
              className="mt-0.5 size-4 shrink-0 text-amber-700 sm:mt-0"
            />
            <p className="text-xs font-semibold leading-relaxed sm:text-sm">
              {info.footer.prototypeNotice}
            </p>
          </div>
          <p className="text-xs leading-relaxed text-amber-900/90 sm:text-right">
            {info.footer.syntheticNote}
          </p>
        </div>
      </div>
    </footer>
  );
}
