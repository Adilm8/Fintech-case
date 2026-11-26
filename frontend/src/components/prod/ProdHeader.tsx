"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Loader2, LogOut, Menu, X } from "lucide-react";
import { NotificationBell } from "@/components/prod/NotificationBell";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { LANG_OPTIONS, useT } from "@/i18n";
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

  const navItems: Array<{
    href: string;
    label: string;
    active: boolean;
    badge: number | null;
  }> = [];

  if (role === "director") {
    navItems.push({
      href: "/director",
      label: t.prod.nav.director,
      active: pathname.startsWith("/director"),
      badge: pendingApprovalsCount,
    });
  }

  navItems.push({
    href: "/payments",
    label: t.prod.nav.payments,
    active: pathname.startsWith("/payments"),
    badge: null,
  });

  navItems.push({
    href: "/suppliers",
    label: t.prod.nav.suppliers,
    active: pathname.startsWith("/suppliers"),
    badge: null,
  });

  if (role === "accountant" || role === "director") {
    navItems.push({
      href: "/company",
      label: t.prod.nav.company,
      active: pathname.startsWith("/company"),
      badge: null,
    });
  }

  if (role === "director" || role === "analyst") {
    navItems.push({
      href: "/audit",
      label: t.prod.nav.audit,
      active: pathname.startsWith("/audit"),
      badge: null,
    });
  }

  if (role === "director") {
    navItems.push({
      href: "/settings",
      label: t.prod.nav.settings,
      active: pathname.startsWith("/settings"),
      badge: null,
    });
  }

  if (role === "analyst") {
    navItems.push({
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

  return (
    <header className="relative z-30 border-b border-border bg-card md:sticky md:top-0">
      <div className="mx-auto w-full max-w-[1248px] px-4 sm:px-6">
        {/* Top bar — stays compact and overflow-free from 360px phone through 800px tablet to 1920px desktop */}
        <div className="flex items-center justify-between gap-2 py-2.5 sm:gap-3">
          <div className="flex min-w-0 flex-1 items-center gap-3">
            <Link
              href={homeHref}
              className="flex min-h-11 min-w-0 shrink-0 items-center gap-2 rounded-[6px] text-left transition-opacity hover:opacity-85 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:min-h-9"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/logo.svg"
                alt=""
                width={28}
                height={28}
                className="h-7 w-7 shrink-0"
              />
              <span className="truncate text-[15px] font-semibold tracking-tight text-foreground">
                {t.brand.name}
              </span>
            </Link>

            <div className="hidden min-w-0 items-center border-l border-border pl-3 md:flex">
              <span className="truncate text-[13px] text-muted-foreground">
                {companyLabel}
              </span>
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-1.5 sm:gap-2">
            <NotificationBell role={role} />

            {/* Desktop profile link (lg+) */}
            <Link
              href="/profile"
              aria-current={isProfileActive ? "page" : undefined}
              title={t.prod.nav.profile}
              className={cn(
                "hidden h-8 min-w-0 items-center gap-1.5 rounded-[6px] border px-2.5 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring lg:inline-flex",
                isProfileActive
                  ? "border-foreground bg-muted text-foreground"
                  : "border-border bg-card text-foreground hover:bg-muted"
              )}
            >
              <span className="max-w-[140px] truncate font-medium">
                {session.user.full_name}
              </span>
              <span aria-hidden="true" className="text-muted-foreground">
                ·
              </span>
              <span className="shrink-0 text-muted-foreground">{roleLabel}</span>
            </Link>

            {/* Language switcher: shown inline on sm+ (tablet & desktop), inside menu on narrow phones */}
            <div
              className="hidden items-center rounded-[6px] border border-border bg-muted p-0.5 sm:inline-flex"
              role="group"
              aria-label={t.nav.langAriaLabel}
            >
              {LANG_OPTIONS.map((option) => {
                const isSelected = lang === option.code;
                return (
                  <button
                    key={option.code}
                    type="button"
                    aria-pressed={isSelected}
                    onClick={() => setLang(option.code)}
                    className={cn(
                      "inline-flex min-h-9 w-[40px] cursor-pointer items-center justify-center rounded-[4px] border text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:min-h-7",
                      isSelected
                        ? "border-border bg-card text-foreground"
                        : "border-transparent text-muted-foreground hover:text-foreground"
                    )}
                  >
                    {option.label}
                  </button>
                );
              })}
            </div>

            {/* Desktop logout button (lg+) */}
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
                    className="hidden size-8 shrink-0 p-0 text-muted-foreground hover:text-foreground lg:inline-flex"
                  />
                }
              >
                {isLoggingOut ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <LogOut className="size-4" />
                )}
              </TooltipTrigger>
              <TooltipContent side="bottom">{t.prod.nav.logout}</TooltipContent>
            </Tooltip>

            {/* Collapsible menu button for phone and tablet (< lg, prevents ~800px horizontal overflow) */}
            <Button
              type="button"
              variant="outline"
              size="icon"
              onClick={() => setMenuOpen((prev) => !prev)}
              aria-expanded={menuOpen}
              aria-controls="prod-mobile-menu"
              aria-label={menuOpen ? t.prod.nav.closeMenu : t.prod.nav.menu}
              className={cn(
                "relative inline-flex size-11 shrink-0 p-0 text-muted-foreground hover:text-foreground sm:size-8 lg:hidden",
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
        </div>

        {/* Desktop navigation tabs (lg+, matches AppHeader style) */}
        <nav
          aria-label={t.nav.ariaLabel}
          className="ui-tabs no-scrollbar hidden border-t border-border border-b-0 lg:flex"
        >
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              aria-current={item.active ? "page" : undefined}
              className="ui-tab mb-0 min-h-10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <span>{item.label}</span>
              {item.badge !== null && (
                <span
                  className={
                    item.badge > 0 ? "ui-tag tabular-nums" : "ui-tab-count"
                  }
                >
                  {item.badge}
                </span>
              )}
            </Link>
          ))}
        </nav>

        {/* Collapsible mobile & tablet navigation menu (< lg) */}
        {menuOpen && (
          <div
            id="prod-mobile-menu"
            className="space-y-3 border-t border-border py-3 lg:hidden"
          >
            {/* Company & user summary */}
            <div className="flex flex-col gap-2 rounded-[6px] border border-border bg-muted/40 px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between">
              <span className="truncate text-xs text-muted-foreground">
                {companyLabel}
              </span>

              <Link
                href="/profile"
                onClick={() => setMenuOpen(false)}
                className={cn(
                  "inline-flex min-h-10 items-center gap-1.5 rounded-[6px] border px-2.5 py-1 text-xs transition-colors sm:min-h-8",
                  isProfileActive
                    ? "border-foreground bg-muted text-foreground"
                    : "border-border bg-card text-foreground hover:bg-muted"
                )}
              >
                <span className="truncate font-medium">
                  {session.user.full_name}
                </span>
                <span aria-hidden="true" className="text-muted-foreground">
                  ·
                </span>
                <span className="shrink-0 text-muted-foreground">
                  {roleLabel}
                </span>
              </Link>
            </div>

            {/* Navigation links */}
            <nav
              aria-label={t.nav.ariaLabel}
              className="grid grid-cols-1 gap-1 sm:grid-cols-2"
            >
              {navItems.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => setMenuOpen(false)}
                  aria-current={item.active ? "page" : undefined}
                  className={cn(
                    "flex min-h-11 items-center justify-between gap-2 rounded-[6px] px-3 py-2 text-sm transition-colors",
                    item.active
                      ? "bg-muted font-semibold text-foreground"
                      : "font-medium text-muted-foreground hover:bg-muted/60 hover:text-foreground"
                  )}
                >
                  <span className="truncate">{item.label}</span>
                  {item.badge !== null && (
                    <span
                      className={
                        item.badge > 0 ? "ui-tag tabular-nums" : "ui-tab-count"
                      }
                    >
                      {item.badge}
                    </span>
                  )}
                </Link>
              ))}

              <Link
                href="/profile"
                onClick={() => setMenuOpen(false)}
                aria-current={isProfileActive ? "page" : undefined}
                className={cn(
                  "flex min-h-11 items-center gap-2 rounded-[6px] px-3 py-2 text-sm transition-colors",
                  isProfileActive
                    ? "bg-muted font-semibold text-foreground"
                    : "font-medium text-muted-foreground hover:bg-muted/60 hover:text-foreground"
                )}
              >
                <span>{t.prod.nav.profile}</span>
              </Link>
            </nav>

            {/* Language switcher on narrow phones + Logout */}
            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-3">
              <div
                className="inline-flex items-center rounded-[6px] border border-border bg-muted p-0.5 sm:hidden"
                role="group"
                aria-label={t.nav.langAriaLabel}
              >
                {LANG_OPTIONS.map((option) => {
                  const isSelected = lang === option.code;
                  return (
                    <button
                      key={option.code}
                      type="button"
                      aria-pressed={isSelected}
                      onClick={() => setLang(option.code)}
                      className={cn(
                        "inline-flex min-h-9 w-[42px] cursor-pointer items-center justify-center rounded-[4px] border text-xs font-medium transition-colors",
                        isSelected
                          ? "border-border bg-card text-foreground"
                          : "border-transparent text-muted-foreground hover:text-foreground"
                      )}
                    >
                      {option.label}
                    </button>
                  );
                })}
              </div>

              <Button
                type="button"
                variant="outline"
                onClick={() => void handleLogoutClick()}
                disabled={isLoggingOut}
                className="min-h-11 sm:ml-auto sm:min-h-8"
              >
                {isLoggingOut && <Loader2 className="size-4 animate-spin" />}
                <span>
                  {isLoggingOut ? t.prod.nav.loggingOut : t.prod.nav.logout}
                </span>
              </Button>
            </div>
          </div>
        )}
      </div>
    </header>
  );
}
