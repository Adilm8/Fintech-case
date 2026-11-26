"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BadgeCheck,
  BarChart3,
  Building2,
  ClipboardCheck,
  FileText,
  Landmark,
  Loader2,
  LogOut,
  Menu,
  ScrollText,
  Settings,
  UserCircle2,
  Users,
  X,
} from "lucide-react";
import { NotificationBell } from "@/components/prod/NotificationBell";
import { Badge } from "@/components/ui/badge";
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
    icon: typeof FileText;
    active: boolean;
    badge: number | null;
  }> = [];

  if (role === "director") {
    navItems.push({
      href: "/director",
      label: t.prod.nav.director,
      icon: ClipboardCheck,
      active: pathname.startsWith("/director"),
      badge: pendingApprovalsCount,
    });
  }

  navItems.push({
    href: "/payments",
    label: t.prod.nav.payments,
    icon: FileText,
    active: pathname.startsWith("/payments"),
    badge: null,
  });

  navItems.push({
    href: "/suppliers",
    label: t.prod.nav.suppliers,
    icon: Users,
    active: pathname.startsWith("/suppliers"),
    badge: null,
  });

  if (role === "accountant" || role === "director") {
    navItems.push({
      href: "/company",
      label: t.prod.nav.company,
      icon: Building2,
      active: pathname.startsWith("/company"),
      badge: null,
    });
  }

  if (role === "director" || role === "analyst") {
    navItems.push({
      href: "/audit",
      label: t.prod.nav.audit,
      icon: ScrollText,
      active: pathname.startsWith("/audit"),
      badge: null,
    });
  }

  if (role === "director") {
    navItems.push({
      href: "/settings",
      label: t.prod.nav.settings,
      icon: Settings,
      active: pathname.startsWith("/settings"),
      badge: null,
    });
  }

  if (role === "analyst") {
    navItems.push({
      href: "/analytics",
      label: t.prod.nav.analytics,
      icon: BarChart3,
      active: pathname.startsWith("/analytics"),
      badge: null,
    });
  }

  const isProfileActive = pathname.startsWith("/profile");
  const companyLabel =
    session.company?.name ?? t.prod.roles.bankAnalystCompany;
  const roleLabel = t.prod.roles[role];

  return (
    <header className="relative z-30 border-b border-border bg-card/95 shadow-[0_1px_2px_rgba(29,29,30,0.03)] backdrop-blur supports-[backdrop-filter]:bg-card/90 md:sticky md:top-0">
      <div className="mx-auto w-full max-w-[1248px] px-4 sm:px-6">
        {/* Top bar — stays compact and overflow-free from 360px phone through 800px tablet to 1920px desktop */}
        <div className="flex items-center justify-between gap-2 py-2.5 sm:gap-3 sm:py-3">
          <div className="flex min-w-0 flex-1 items-center gap-3">
            <Link
              href={homeHref}
              className="flex min-h-11 min-w-0 items-center gap-2.5 rounded-lg text-left transition-opacity hover:opacity-85 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:min-h-10"
            >
              <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-[0_2px_8px_rgba(0,171,117,0.28)]">
                <BadgeCheck className="size-5" />
              </div>
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold leading-tight tracking-tight text-foreground sm:text-base">
                  {t.brand.name}
                </div>
                <div className="hidden truncate text-xs leading-snug text-muted-foreground xl:block">
                  {t.brand.subtitle}
                </div>
              </div>
            </Link>

            <div className="hidden min-w-0 items-center border-l border-border pl-3.5 xl:flex">
              <div className="inline-flex max-w-[230px] min-w-0 items-center gap-2 rounded-xl border border-border bg-background px-3 py-1.5 text-sm">
                {session.company ? (
                  <Building2 className="size-4 shrink-0 text-muted-foreground" />
                ) : (
                  <Landmark className="size-4 shrink-0 text-[var(--brand-text)]" />
                )}
                <span className="truncate font-medium text-foreground">
                  {companyLabel}
                </span>
              </div>
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-1.5 sm:gap-2">
            <NotificationBell role={role} />

            {/* Desktop profile chip (lg+) */}
            <Link
              href="/profile"
              aria-current={isProfileActive ? "page" : undefined}
              title={t.prod.nav.profile}
              className={cn(
                "hidden min-w-0 items-center gap-2 rounded-xl border px-2.5 py-1.5 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring lg:inline-flex",
                isProfileActive
                  ? "border-primary/50 bg-accent/70 text-accent-foreground"
                  : "border-border bg-background hover:bg-muted/70"
              )}
            >
              <UserCircle2
                className={cn(
                  "size-4 shrink-0",
                  isProfileActive
                    ? "text-[var(--brand-text)]"
                    : "text-muted-foreground"
                )}
              />
              <span className="max-w-[140px] truncate font-medium text-foreground">
                {session.user.full_name}
              </span>
              <Badge
                variant="secondary"
                className="h-auto px-1.5 py-0.5 text-[11px] font-medium"
              >
                {roleLabel}
              </Badge>
            </Link>

            {/* Language switcher: shown inline on sm+ (tablet & desktop), inside menu on narrow phones */}
            <div
              className="hidden items-center rounded-xl border border-border bg-background p-0.5 sm:inline-flex"
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
                      "inline-flex min-h-8 w-[40px] cursor-pointer items-center justify-center rounded-[10px] text-xs font-semibold tracking-wide transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      isSelected
                        ? "bg-card text-[var(--brand-text)] shadow-xs ring-1 ring-border/70"
                        : "text-muted-foreground hover:text-foreground"
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
                    className="hidden size-9 shrink-0 p-0 text-muted-foreground hover:text-foreground lg:inline-flex"
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
                "relative inline-flex size-11 shrink-0 p-0 text-muted-foreground hover:text-foreground sm:size-9 lg:hidden",
                menuOpen && "border-primary/50 bg-accent/60 text-foreground"
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
                  className="absolute top-1.5 right-1.5 size-2 rounded-full bg-amber-500 ring-2 ring-card"
                />
              )}
            </Button>
          </div>
        </div>

        {/* Desktop navigation bar (lg+, wraps cleanly with zero horizontal overflow) */}
        <nav
          aria-label={t.nav.ariaLabel}
          className="hidden flex-wrap items-center gap-1 border-t border-border/70 py-1.5 lg:flex"
        >
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={item.active ? "page" : undefined}
                className={cn(
                  "relative inline-flex min-h-9 shrink-0 items-center gap-2 whitespace-nowrap rounded-xl px-3 py-1.5 text-sm transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  item.active
                    ? "bg-accent font-semibold text-accent-foreground"
                    : "font-medium text-muted-foreground hover:bg-muted/80 hover:text-foreground"
                )}
              >
                <Icon
                  className={cn(
                    "size-4 shrink-0",
                    item.active
                      ? "text-[var(--brand-text)]"
                      : "text-muted-foreground"
                  )}
                />
                <span>{item.label}</span>
                {item.badge !== null && (
                  <Badge
                    variant={item.badge > 0 ? "default" : "secondary"}
                    className={cn(
                      "h-auto min-h-5 min-w-5 px-1.5 py-0.5 text-xs tabular-nums",
                      item.badge > 0
                        ? "border-transparent bg-amber-500 text-white hover:bg-amber-500"
                        : item.active
                          ? "border-transparent bg-primary/15 text-accent-foreground"
                          : "border-border bg-background text-muted-foreground"
                    )}
                  >
                    {item.badge}
                  </Badge>
                )}
                {item.active && (
                  <span
                    aria-hidden="true"
                    className="absolute inset-x-3 -bottom-1.5 h-0.5 rounded-full bg-primary"
                  />
                )}
              </Link>
            );
          })}
        </nav>

        {/* Collapsible mobile & tablet navigation menu (< lg) */}
        {menuOpen && (
          <div
            id="prod-mobile-menu"
            className="space-y-3 border-t border-border/70 py-3 lg:hidden"
          >
            {/* Company & user profile card */}
            <div className="flex flex-col gap-2 rounded-xl border border-border bg-background/80 p-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex min-w-0 items-center gap-2 text-xs">
                {session.company ? (
                  <Building2 className="size-4 shrink-0 text-muted-foreground" />
                ) : (
                  <Landmark className="size-4 shrink-0 text-[var(--brand-text)]" />
                )}
                <span className="truncate font-medium text-foreground">
                  {companyLabel}
                </span>
              </div>

              <Link
                href="/profile"
                onClick={() => setMenuOpen(false)}
                className={cn(
                  "inline-flex min-h-10 items-center gap-2 rounded-xl border px-3 py-1.5 text-xs font-medium transition-colors sm:min-h-9",
                  isProfileActive
                    ? "border-primary/50 bg-accent text-accent-foreground"
                    : "border-border bg-card text-foreground hover:bg-muted/60"
                )}
              >
                <UserCircle2 className="size-4 shrink-0 text-[var(--brand-text)]" />
                <span className="truncate">{session.user.full_name}</span>
                <Badge
                  variant="secondary"
                  className="h-auto px-1.5 py-0.5 text-[11px]"
                >
                  {roleLabel}
                </Badge>
              </Link>
            </div>

            {/* Navigation links */}
            <nav
              aria-label={t.nav.ariaLabel}
              className="grid grid-cols-1 gap-1 sm:grid-cols-2"
            >
              {navItems.map((item) => {
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setMenuOpen(false)}
                    aria-current={item.active ? "page" : undefined}
                    className={cn(
                      "flex min-h-11 items-center justify-between gap-2 rounded-xl px-3.5 py-2 text-sm transition-colors",
                      item.active
                        ? "bg-accent font-semibold text-accent-foreground"
                        : "font-medium text-muted-foreground hover:bg-muted/80 hover:text-foreground"
                    )}
                  >
                    <span className="flex min-w-0 items-center gap-2.5">
                      <Icon
                        className={cn(
                          "size-4 shrink-0",
                          item.active
                            ? "text-[var(--brand-text)]"
                            : "text-muted-foreground"
                        )}
                      />
                      <span className="truncate">{item.label}</span>
                    </span>
                    {item.badge !== null && (
                      <Badge
                        variant={item.badge > 0 ? "default" : "secondary"}
                        className={cn(
                          "h-auto min-h-5 min-w-5 px-1.5 py-0.5 text-xs tabular-nums",
                          item.badge > 0
                            ? "border-transparent bg-amber-500 text-white"
                            : "border-border bg-background text-muted-foreground"
                        )}
                      >
                        {item.badge}
                      </Badge>
                    )}
                  </Link>
                );
              })}

              <Link
                href="/profile"
                onClick={() => setMenuOpen(false)}
                aria-current={isProfileActive ? "page" : undefined}
                className={cn(
                  "flex min-h-11 items-center gap-2.5 rounded-xl px-3.5 py-2 text-sm transition-colors",
                  isProfileActive
                    ? "bg-accent font-semibold text-accent-foreground"
                    : "font-medium text-muted-foreground hover:bg-muted/80 hover:text-foreground"
                )}
              >
                <UserCircle2
                  className={cn(
                    "size-4 shrink-0",
                    isProfileActive
                      ? "text-[var(--brand-text)]"
                      : "text-muted-foreground"
                  )}
                />
                <span>{t.prod.nav.profile}</span>
              </Link>
            </nav>

            {/* Language switcher on narrow phones + Logout */}
            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border/70 pt-3">
              <div
                className="inline-flex items-center rounded-xl border border-border bg-background p-0.5 sm:hidden"
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
                        "inline-flex min-h-9 w-[44px] cursor-pointer items-center justify-center rounded-[10px] text-xs font-semibold tracking-wide transition-all",
                        isSelected
                          ? "bg-card text-[var(--brand-text)] shadow-xs ring-1 ring-border/70"
                          : "text-muted-foreground hover:text-foreground"
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
                className="min-h-11 gap-2 rounded-xl sm:ml-auto sm:min-h-9"
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
    </header>
  );
}
