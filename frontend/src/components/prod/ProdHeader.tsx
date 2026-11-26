"use client";

import { useEffect, useRef, useState } from "react";
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
  ScrollText,
  UserCircle2,
  Users,
} from "lucide-react";
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
  const activeTabRef = useRef<HTMLAnchorElement | null>(null);

  const role = session.user.role;
  const homeHref = defaultHomeForRole(role);

  useEffect(() => {
    const el = activeTabRef.current;
    if (el && typeof el.scrollIntoView === "function") {
      el.scrollIntoView({
        behavior: "smooth",
        inline: "center",
        block: "nearest",
      });
    }
  }, [pathname, lang]);

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

  if (role === "director" || role === "analyst") {
    navItems.push({
      href: "/audit",
      label: t.prod.nav.audit,
      icon: ScrollText,
      active: pathname.startsWith("/audit"),
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

  const companyLabel =
    session.company?.name ?? t.prod.roles.bankAnalystCompany;
  const roleLabel = t.prod.roles[role];

  return (
    <header className="relative z-30 border-b border-border bg-card/95 shadow-[0_1px_2px_rgba(29,29,30,0.03)] backdrop-blur supports-[backdrop-filter]:bg-card/90 md:sticky md:top-0">
      <div className="mx-auto w-full max-w-[1248px] px-4 sm:px-6">
        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2.5 py-3">
          <div className="flex min-w-0 flex-1 items-center gap-3 sm:gap-4">
            <Link
              href={homeHref}
              className="flex min-h-11 min-w-0 shrink-0 items-center gap-2.5 rounded-lg text-left transition-opacity hover:opacity-85 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:min-h-10"
            >
              <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-[0_2px_8px_rgba(0,171,117,0.28)]">
                <BadgeCheck className="size-5" />
              </div>
              <div className="min-w-0">
                <div className="text-sm font-semibold leading-tight tracking-tight text-foreground sm:text-base">
                  {t.brand.name}
                </div>
                <div className="hidden text-xs leading-snug text-muted-foreground sm:block">
                  {t.brand.subtitle}
                </div>
              </div>
            </Link>

            <div className="hidden min-w-0 items-center border-l border-border pl-4 lg:flex">
              <div className="inline-flex max-w-[260px] min-w-0 items-center gap-2 rounded-xl border border-border bg-background px-3 py-1.5 text-sm">
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

          <div className="flex shrink-0 items-center gap-2 sm:gap-2.5">
            <div className="hidden min-w-0 items-center gap-2 rounded-xl border border-border bg-background px-2.5 py-1.5 text-xs md:inline-flex">
              <UserCircle2 className="size-4 shrink-0 text-muted-foreground" />
              <span className="max-w-[160px] truncate font-medium text-foreground">
                {session.user.full_name}
              </span>
              <Badge
                variant="secondary"
                className="h-auto px-1.5 py-0.5 text-[11px] font-medium"
              >
                {roleLabel}
              </Badge>
            </div>

            <div
              className="inline-flex items-center rounded-xl border border-border bg-background p-0.5"
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
                      "inline-flex min-h-9 w-[42px] cursor-pointer items-center justify-center rounded-[10px] text-xs font-semibold tracking-wide transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:min-h-8",
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
                    className="size-11 shrink-0 p-0 text-muted-foreground hover:text-foreground sm:size-9"
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
          </div>

          <div className="flex w-full min-w-0 flex-wrap items-center justify-between gap-2 lg:hidden">
            <div className="inline-flex max-w-full min-w-0 items-center gap-2 rounded-xl border border-border bg-background px-2.5 py-1 text-xs">
              {session.company ? (
                <Building2 className="size-3.5 shrink-0 text-muted-foreground" />
              ) : (
                <Landmark className="size-3.5 shrink-0 text-[var(--brand-text)]" />
              )}
              <span className="truncate font-medium text-foreground">
                {companyLabel}
              </span>
            </div>

            <div className="inline-flex min-w-0 items-center gap-1.5 rounded-xl border border-border bg-background px-2.5 py-1 text-xs md:hidden">
              <UserCircle2 className="size-3.5 shrink-0 text-muted-foreground" />
              <span className="max-w-[140px] truncate font-medium text-foreground">
                {session.user.full_name}
              </span>
              <span className="text-muted-foreground">·</span>
              <span className="shrink-0 text-muted-foreground">
                {roleLabel}
              </span>
            </div>
          </div>
        </div>

        <nav
          aria-label={t.nav.ariaLabel}
          className="no-scrollbar -mx-4 flex items-center gap-1 overflow-x-auto border-t border-border/70 px-4 py-1.5 sm:mx-0 sm:px-0"
        >
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                ref={item.active ? activeTabRef : undefined}
                href={item.href}
                aria-current={item.active ? "page" : undefined}
                className={cn(
                  "relative inline-flex min-h-11 shrink-0 items-center gap-2 whitespace-nowrap rounded-xl px-3.5 py-2 text-sm transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:min-h-9 sm:py-1.5",
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
      </div>
    </header>
  );
}
