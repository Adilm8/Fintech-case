"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Keyboard, Loader2, RotateCcw } from "lucide-react";
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
      active: pathname === "/" || pathname.startsWith("/check"),
      badge: null as number | null,
    },
    {
      href: "/approvals",
      label: t.nav.approvals,
      active: pathname.startsWith("/approvals"),
      badge: pendingCount,
    },
    {
      href: "/history",
      label: t.nav.history,
      active: pathname.startsWith("/history"),
      badge: null as number | null,
    },
    {
      href: "/attack",
      label: t.nav.attack,
      active: pathname.startsWith("/attack"),
      badge: null as number | null,
    },
    {
      href: "/metrics",
      label: t.nav.metrics,
      active: pathname.startsWith("/metrics"),
      badge: null as number | null,
    },
  ];

  return (
    <header className="relative z-30 border-b border-border bg-card md:sticky md:top-0">
      <div className="mx-auto w-full max-w-[1248px] px-4 sm:px-6">
        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 py-2.5">
          <div className="flex min-w-0 flex-1 items-center gap-3">
            <Link
              href="/"
              onClick={() => {
                if (pathname === "/") {
                  onHomeReset?.();
                }
              }}
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
                {t.brand.companyName}
              </span>
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-2">
            <div
              className="inline-flex items-center rounded-[6px] border border-border bg-muted p-0.5"
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
                      "inline-flex min-h-9 w-[40px] items-center justify-center rounded-[4px] border text-xs font-medium transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:min-h-7",
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
                      className="hidden size-8 shrink-0 p-0 text-muted-foreground hover:text-foreground sm:inline-flex"
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
                    className="size-11 shrink-0 p-0 text-muted-foreground hover:text-foreground sm:size-8"
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
            <span className="truncate text-xs text-muted-foreground">
              {t.brand.companyName}
            </span>
          </div>
        </div>

        <nav
          aria-label={t.nav.ariaLabel}
          className="ui-tabs no-scrollbar -mx-4 border-t border-border border-b-0 px-4 sm:mx-0 sm:px-0"
        >
          {navItems.map((item) => (
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
              className="ui-tab mb-0 min-h-11 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:min-h-10"
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
                <span>{t.nav.resetConfirmAction}</span>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </header>
  );
}
