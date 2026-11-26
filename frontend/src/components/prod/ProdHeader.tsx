"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Loader2, LogOut, Menu, X } from "lucide-react";
import {
  BrandLogo,
  CompanyChip,
  LanguageSwitch,
} from "@/components/nav/HeaderControls";
import { NavTileList, type NavTileItem } from "@/components/nav/NavTile";
import { NotificationBell } from "@/components/prod/NotificationBell";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useT } from "@/i18n";
import { defaultHomeForRole } from "@/lib/prod/session";
import type { Session } from "@/lib/prod/types";
import { cn } from "cn";

interface ProdHeaderProps {
  session: Session;
  pendingApprovalsCount: number;
  onLogout: () => Promise<void>;
}

export function ProdHeader({
  session,
  pendingApprovalsCount,
  onLogout,
}: ProdHeaderProps) {
  const pathname = usePathname();
  const { t, lang, setLang } = useT();
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [menuState, setMenuState] = useState<{
    pathname: string;
    open: boolean;
  }>({ pathname, open: false });

  const menuOpen = menuState.pathname === pathname && menuState.open;
  const setMenuOpen = (next: boolean | ((prev: boolean) => boolean)) => {
    setMenuState((prev) => {
      const currentOpen = prev.pathname === pathname && prev.open;
      const resolved = typeof next === "function" ? next(currentOpen) : next;
      return { pathname, open: resolved };
    });
  };

  const role = session.user.role;
  const homeHref = defaultHomeForRole(role);

  useEffect(() => {
    if (!menuOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuState((prev) => ({ ...prev, open: false }));
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [menuOpen]);

  const handleLogoutClick = async () => {
    if (isLoggingOut) return;
    setIsLoggingOut(true);
    try {
      await onLogout();
    } finally {
      setIsLoggingOut(false);
    }
  };

  const navItems: NavTileItem[] = [];

  if (role === "director") {
    navItems.push({
      key: "approvals",
      href: "/director",
      label: t.prod.nav.director,
      active: pathname.startsWith("/director"),
      badge: pendingApprovalsCount,
    });
  }

  navItems.push({
    key: "payments",
    href: "/payments",
    label: t.prod.nav.payments,
    active: pathname.startsWith("/payments"),
    badge: null,
  });

  navItems.push({
    key: "suppliers",
    href: "/suppliers",
    label: t.prod.nav.suppliers,
    active: pathname.startsWith("/suppliers"),
    badge: null,
  });

  if (role === "accountant" || role === "director") {
    navItems.push({
      key: "company",
      href: "/company",
      label: t.prod.nav.company,
      active: pathname.startsWith("/company"),
      badge: null,
    });
  }

  if (role === "director" || role === "analyst") {
    navItems.push({
      key: "audit",
      href: "/audit",
      label: t.prod.nav.audit,
      active: pathname.startsWith("/audit"),
      badge: null,
    });
  }

  if (role === "director") {
    navItems.push({
      key: "settings",
      href: "/settings",
      label: t.prod.nav.settings,
      active: pathname.startsWith("/settings"),
      badge: null,
    });
  }

  if (role === "analyst") {
    navItems.push({
      key: "metrics",
      href: "/analytics",
      label: t.prod.nav.analytics,
      active: pathname.startsWith("/analytics"),
      badge: null,
    });
  }

  const isProfileActive = pathname.startsWith("/profile");
  const companyLabel =
    session.company?.name ?? t.prod.roles.bankAnalystCompany;
  const roleLabel = t.prod.roles[role];
  const profileTitle = `${session.user.full_name} · ${roleLabel}`;

  return (
    <header className="hdr-shell">
      <div className="mx-auto w-full max-w-[1248px] px-4 sm:px-6">
        <div className="hdr-card px-2.5 py-2 md:px-4 md:py-2.5">
          <div className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-2 md:grid-cols-[minmax(0,1fr)_auto] md:gap-x-3">
            {/* Brand + company chip */}
            <div className="order-1 flex min-w-0 items-center gap-3">
              <BrandLogo href={homeHref} name={t.brand.name} />
              <CompanyChip
                name={companyLabel}
                className="hidden max-w-[160px] md:inline-flex lg:max-w-[240px] xl:max-w-[320px]"
              />
            </div>

            {/* Right controls */}
            <div className="order-3 flex shrink-0 items-center gap-1.5 md:order-2 md:gap-2">
              <NotificationBell role={role} />

              {/* Profile & role chip (md+) */}
              <Link
                href="/profile"
                aria-current={isProfileActive ? "page" : undefined}
                title={profileTitle}
                className={cn(
                  "hidden h-8 min-w-0 items-center gap-1.5 rounded-[10px] border px-2.5 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring md:inline-flex",
                  isProfileActive
                    ? "border-[#1D1D1E] bg-[#1D1D1E] text-white"
                    : "border-border bg-card text-foreground hover:bg-muted"
                )}
              >
                <span className="max-w-[104px] truncate font-medium lg:max-w-[140px]">
                  {session.user.full_name}
                </span>
                <span
                  aria-hidden="true"
                  className={cn(
                    "hidden lg:inline",
                    isProfileActive ? "text-white/60" : "text-muted-foreground"
                  )}
                >
                  ·
                </span>
                <span
                  className={cn(
                    "hidden shrink-0 lg:inline",
                    isProfileActive ? "text-white/80" : "text-muted-foreground"
                  )}
                >
                  {roleLabel}
                </span>
              </Link>

              {/* Language switch (md+) */}
              <LanguageSwitch
                lang={lang}
                onChange={setLang}
                ariaLabel={t.nav.langAriaLabel}
                className="hidden md:inline-flex"
              />

              {/* Logout icon button (md+) */}
              <Tooltip>
                <TooltipTrigger
                  render={
                    <Button
                      type="button"
                      variant="outline"
                      size="icon"
                      onClick={() => void handleLogoutClick()}
                      disabled={isLoggingOut}
                      aria-label={
                        isLoggingOut ? t.prod.nav.loggingOut : t.prod.nav.logout
                      }
                      title={
                        isLoggingOut ? t.prod.nav.loggingOut : t.prod.nav.logout
                      }
                      className="hidden size-8 shrink-0 rounded-[10px] p-0 text-muted-foreground hover:text-foreground md:inline-flex"
                    />
                  }
                >
                  {isLoggingOut ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <LogOut className="size-4" />
                  )}
                </TooltipTrigger>
                <TooltipContent side="bottom">
                  {t.prod.nav.logout}
                </TooltipContent>
              </Tooltip>

              {/* Mobile utility drawer button (< md; sized to align cleanly with NotificationBell) */}
              <Button
                type="button"
                variant="outline"
                size="icon"
                onClick={() => setMenuOpen((prev) => !prev)}
                aria-expanded={menuOpen}
                aria-controls="prod-mobile-menu"
                aria-label={menuOpen ? t.prod.nav.closeMenu : t.prod.nav.menu}
                className={cn(
                  "relative inline-flex size-11 shrink-0 rounded-[10px] p-0 text-muted-foreground hover:text-foreground sm:size-8 md:hidden",
                  menuOpen && "border-foreground/30 bg-muted text-foreground"
                )}
              >
                {menuOpen ? (
                  <X className="size-5 sm:size-4" />
                ) : (
                  <Menu className="size-5 sm:size-4" />
                )}
                {!menuOpen && pendingApprovalsCount > 0 && (
                  <span
                    aria-hidden="true"
                    className="absolute top-1.5 right-1.5 size-1.5 rounded-full bg-[var(--status-warn)] ring-2 ring-card"
                  />
                )}
              </Button>
            </div>

            {/* Section navigation tiles (inline scrollable row on < md, full second row on md+) */}
            <NavTileList
              items={navItems}
              ariaLabel={t.nav.ariaLabel}
              scrollKey={`${pathname}:${lang}`}
              className="order-2 md:order-3 md:col-span-2 md:mt-2.5 md:border-t md:border-border/70 md:pt-2.5"
            />

            {/* Collapsible mobile utility panel (< md) */}
            {menuOpen && (
              <div
                id="prod-mobile-menu"
                className="order-4 col-span-3 mt-2.5 space-y-2.5 border-t border-border/70 pt-3 md:hidden"
              >
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <CompanyChip name={companyLabel} className="max-w-full" />

                  <Link
                    href="/profile"
                    onClick={() => setMenuOpen(false)}
                    aria-current={isProfileActive ? "page" : undefined}
                    className={cn(
                      "inline-flex min-h-10 items-center gap-1.5 rounded-[10px] border px-3 py-1 text-xs transition-colors sm:min-h-8",
                      isProfileActive
                        ? "border-[#1D1D1E] bg-[#1D1D1E] text-white"
                        : "border-border bg-card text-foreground hover:bg-muted"
                    )}
                  >
                    <span className="truncate font-medium">
                      {session.user.full_name}
                    </span>
                    <span
                      aria-hidden="true"
                      className={
                        isProfileActive
                          ? "text-white/60"
                          : "text-muted-foreground"
                      }
                    >
                      ·
                    </span>
                    <span
                      className={cn(
                        "shrink-0",
                        isProfileActive
                          ? "text-white/80"
                          : "text-muted-foreground"
                      )}
                    >
                      {roleLabel}
                    </span>
                  </Link>
                </div>

                <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border/70 pt-2.5">
                  <LanguageSwitch
                    lang={lang}
                    onChange={setLang}
                    ariaLabel={t.nav.langAriaLabel}
                  />

                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => void handleLogoutClick()}
                    disabled={isLoggingOut}
                    className="min-h-9 gap-1.5 rounded-[10px] sm:ml-auto sm:min-h-8"
                  >
                    {isLoggingOut ? (
                      <Loader2 className="size-4 animate-spin" />
                    ) : (
                      <LogOut className="size-4" />
                    )}
                    <span>
                      {isLoggingOut ? t.prod.nav.loggingOut : t.prod.nav.logout}
                    </span>
                  </Button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
