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
  History,
  Keyboard,
  Loader2,
  Radar,
  RotateCcw,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { LANG_OPTIONS, useT } from "@/i18n";
import { cn } from "cn";

interface AppHeaderProps {
  pendingCount: number;
  onResetDemo: () => Promise<void> | void;
  isResetting: boolean;
  onHomeReset?: () => void;
  onOpenShortcuts?: () => void;
}

export function AppHeader({
  pendingCount,
  onResetDemo,
  isResetting,
  onHomeReset,
  onOpenShortcuts,
}: AppHeaderProps) {
  const pathname = usePathname();
  const { t, lang, setLang } = useT();
  const [resetDialogOpen, setResetDialogOpen] = useState(false);
  const activeTabRef = useRef<HTMLAnchorElement | null>(null);

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

  const resetLabel = isResetting ? t.nav.resetting : t.nav.resetDemo;

  const handleConfirmReset = async () => {
    if (isResetting) return;
    await onResetDemo();
    setResetDialogOpen(false);
  };

  const navItems = [
    {
      href: "/",
      label: t.nav.payments,
      icon: FileText,
      active: pathname === "/" || pathname.startsWith("/check"),
      badge: null as number | null,
    },
    {
      href: "/approvals",
      label: t.nav.approvals,
      icon: ClipboardCheck,
      active: pathname.startsWith("/approvals"),
      badge: pendingCount,
    },
    {
      href: "/history",
      label: t.nav.history,
      icon: History,
      active: pathname.startsWith("/history"),
      badge: null as number | null,
    },
    {
      href: "/attack",
      label: t.nav.attack,
      icon: Radar,
      active: pathname.startsWith("/attack"),
      badge: null as number | null,
    },
    {
      href: "/metrics",
      label: t.nav.metrics,
      icon: BarChart3,
      active: pathname.startsWith("/metrics"),
      badge: null as number | null,
    },
  ];

  return (
    <header className="relative z-30 border-b border-border bg-card/95 shadow-[0_1px_2px_rgba(29,29,30,0.03)] backdrop-blur supports-[backdrop-filter]:bg-card/90 md:sticky md:top-0">
      <div className="mx-auto w-full max-w-[1248px] px-4 sm:px-6">
        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2.5 py-3">
          <div className="flex min-w-0 flex-1 items-center gap-3 sm:gap-4">
            <Link
              href="/"
              onClick={() => {
                if (pathname === "/") {
                  onHomeReset?.();
                }
              }}
              className="flex min-h-11 min-w-0 items-center gap-2.5 rounded-lg text-left transition-opacity hover:opacity-85 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:min-h-10 shrink-0"
            >
              <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-[0_2px_8px_rgba(0,171,117,0.28)]">
                <BadgeCheck className="size-5" />
              </div>
              <div className="min-w-0">
                <div className="text-sm font-semibold tracking-tight text-foreground leading-tight sm:text-base">
                  {t.brand.name}
                </div>
                <div className="hidden text-xs leading-snug text-muted-foreground sm:block">
                  {t.brand.subtitle}
                </div>
              </div>
            </Link>

            <div className="hidden min-w-0 items-center border-l border-border pl-4 md:flex">
              <div className="inline-flex max-w-full min-w-0 items-center gap-2 rounded-xl border border-border bg-background px-3 py-1.5 text-sm">
                <Building2 className="size-4 shrink-0 text-muted-foreground" />
                <span className="truncate font-medium text-foreground">
                  {t.brand.companyName}
                </span>
              </div>
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-2 sm:gap-2.5">
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
                      "inline-flex min-h-9 w-[42px] items-center justify-center rounded-[10px] text-xs font-semibold tracking-wide transition-all cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:min-h-8",
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

            {onOpenShortcuts && (
              <Tooltip>
                <TooltipTrigger
                  render={
                    <Button
                      type="button"
                      variant="outline"
                      size="icon"
                      onClick={onOpenShortcuts}
                      aria-label={t.nav.shortcutsTooltip}
                      title={t.nav.shortcutsTooltip}
                      className="hidden size-9 shrink-0 p-0 text-muted-foreground hover:text-foreground sm:inline-flex"
                    />
                  }
                >
                  <Keyboard className="size-4" />
                </TooltipTrigger>
                <TooltipContent side="bottom">
                  {t.nav.shortcutsTooltip}
                </TooltipContent>
              </Tooltip>
            )}

            <Tooltip>
              <TooltipTrigger
                render={
                  <Button
                    type="button"
                    variant="outline"
                    size="icon"
                    onClick={() => setResetDialogOpen(true)}
                    disabled={isResetting}
                    aria-label={resetLabel}
                    title={resetLabel}
                    className="size-11 shrink-0 p-0 text-muted-foreground hover:text-foreground sm:size-9"
                  />
                }
              >
                <RotateCcw
                  className={cn("size-4", isResetting && "animate-spin")}
                />
              </TooltipTrigger>
              <TooltipContent side="bottom">{resetLabel}</TooltipContent>
            </Tooltip>
          </div>

          <div className="flex w-full min-w-0 items-center md:hidden">
            <div className="inline-flex max-w-full min-w-0 items-center gap-2 rounded-xl border border-border bg-background px-2.5 py-1 text-xs">
              <Building2 className="size-3.5 shrink-0 text-muted-foreground" />
              <span className="truncate font-medium text-foreground">
                {t.brand.companyName}
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
                onClick={() => {
                  if (item.href === "/" && pathname === "/") {
                    onHomeReset?.();
                  }
                }}
                className={cn(
                  "relative inline-flex min-h-11 shrink-0 items-center gap-2 whitespace-nowrap rounded-xl px-3.5 py-2 text-sm transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:min-h-9 sm:py-1.5",
                  item.active
                    ? "bg-accent text-accent-foreground font-semibold"
                    : "text-muted-foreground font-medium hover:bg-muted/80 hover:text-foreground"
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
                        ? "bg-amber-500 text-white border-transparent hover:bg-amber-500"
                        : item.active
                          ? "bg-primary/15 text-accent-foreground border-transparent"
                          : "bg-background text-muted-foreground border-border"
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

      <Dialog
        open={resetDialogOpen}
        onOpenChange={(nextOpen) => {
          if (!isResetting) {
            setResetDialogOpen(nextOpen);
          }
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t.nav.resetConfirmTitle}</DialogTitle>
            <DialogDescription>
              {t.nav.resetConfirmDescription}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setResetDialogOpen(false)}
              disabled={isResetting}
              className="min-h-11 w-full sm:min-h-9 sm:w-auto"
            >
              {t.common.cancel}
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={() => void handleConfirmReset()}
              disabled={isResetting}
              className="min-h-11 w-full gap-1.5 sm:min-h-9 sm:w-auto"
            >
              {isResetting ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  <span>{t.nav.resetting}</span>
                </>
              ) : (
                <>
                  <RotateCcw className="size-4" />
                  <span>{t.nav.resetConfirmAction}</span>
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </header>
  );
}
