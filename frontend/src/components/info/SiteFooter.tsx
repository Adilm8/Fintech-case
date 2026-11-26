"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useInfoT, type InfoRouteKey } from "@/i18n/info";
import { IS_PROD } from "@/lib/mode";
import { cn } from "cn";

export interface SiteFooterProps {
  /**
   * Set to true when rendered inside <main> (e.g. inside (info)/layout.tsx)
   * so the footer uses inline spacing instead of a full-bleed bottom bar.
   */
  embedded?: boolean;
  className?: string;
}

const FOOTER_LINKS: readonly { key: InfoRouteKey; href: string }[] = [
  { key: "howItWorks", href: "/how-it-works" },
  { key: "help", href: "/help" },
  { key: "security", href: "/security" },
  { key: "support", href: "/support" },
  { key: "about", href: "/about" },
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
      "inline-flex min-h-8 items-center rounded-[4px] text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
      active
        ? "font-medium text-foreground"
        : "text-muted-foreground hover:text-foreground"
    );
  };

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
          "flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between",
          !embedded && "mx-auto w-full max-w-[1248px] px-4 py-4 sm:px-6"
        )}
      >
        <div className="flex flex-col gap-1.5 sm:flex-row sm:flex-wrap sm:items-center sm:gap-x-3 sm:gap-y-1">
          <Link
            href={appHomeHref}
            className="inline-flex w-fit items-center gap-2 rounded-[4px] transition-opacity hover:opacity-85 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/logo.svg"
              alt=""
              width={20}
              height={20}
              className="h-5 w-5 shrink-0"
            />
            <span className="text-[13px] font-semibold text-foreground">
              {appT.brand.name}
            </span>
          </Link>
          <span className="text-xs text-muted-foreground">
            {info.footer.prototypeNotice}
          </span>
        </div>

        <nav
          aria-label={info.common.footerNavAria}
          className="flex flex-wrap items-center gap-x-4 gap-y-1"
        >
          <Link href={appHomeHref} className={linkClass(appHomeHref)}>
            {info.footer.backToPayments}
          </Link>
          {FOOTER_LINKS.map((item) => (
            <Link key={item.href} href={item.href} className={linkClass(item.href)}>
              {info.nav[item.key]}
            </Link>
          ))}
        </nav>
      </div>
    </footer>
  );
}
