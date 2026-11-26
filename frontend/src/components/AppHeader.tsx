"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { Keyboard, Loader2, Menu, RotateCcw, X } from "lucide-react";
import {
  BrandLogo,
  CompanyChip,
  LanguageSwitch,
} from "@/components/nav/HeaderControls";
import { NavTileList, type NavTileItem } from "@/components/nav/NavTile";
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
import { useT } from "@/i18n";
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

  const resetLabel = isResetting ? t.nav.resetting : t.nav.resetDemo;

  const handleConfirmReset = async () => {
    if (isResetting) return;
    await onResetDemo();
    setResetDialogOpen(false);
  };

  const handleHomeClick = () => {
    if (pathname === "/") {
      onHomeReset?.();
    }
  };

  const navItems: NavTileItem[] = [
    {
      key: "payments",
      href: "/",
      label: t.nav.payments,
      active: pathname === "/" || pathname.startsWith("/check"),
      badge: null,
      onClick: handleHomeClick,
    },
    {
      key: "approvals",
      href: "/approvals",
      label: t.nav.approvals,
      active: pathname.startsWith("/approvals"),
      badge: pendingCount,
    },
    {
      key: "history",
      href: "/history",
      label: t.nav.history,
      active: pathname.startsWith("/history"),
      badge: null,
    },
    {
      key: "attack",
      href: "/attack",
      label: t.nav.attack,
      active: pathname.startsWith("/attack"),
      badge: null,
    },
    {
      key: "metrics",
      href: "/metrics",
      label: t.nav.metrics,
      active: pathname.startsWith("/metrics"),
      badge: null,
    },
  ];

  return (
    <header className="hdr-shell">
      <div className="mx-auto w-full max-w-[1248px] px-4 sm:px-6">
        <div className="hdr-card px-2.5 py-2 md:px-4 md:py-2.5">
          <div className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-2 md:grid-cols-[minmax(0,1fr)_auto] md:gap-x-3">
            {/* Brand + company chip */}
            <div className="order-1 flex min-w-0 items-center gap-3">
              <BrandLogo
                href="/"
                name={t.brand.name}
                onClick={handleHomeClick}
              />
              <CompanyChip
                name={t.brand.companyName}
                className="hidden max-w-[260px] md:inline-flex lg:max-w-[340px]"
              />
            </div>

            {/* Right controls (language switch + existing icon buttons; mobile utility toggle on < md) */}
            <div className="order-3 flex shrink-0 items-center gap-1.5 md:order-2 md:gap-2">
              <LanguageSwitch
                lang={lang}
                onChange={setLang}
                ariaLabel={t.nav.langAriaLabel}
                className="hidden md:inline-flex"
              />

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
                        className="hidden size-8 shrink-0 rounded-[10px] p-0 text-muted-foreground hover:text-foreground md:inline-flex"
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
                      className="size-10 shrink-0 rounded-[10px] p-0 text-muted-foreground hover:text-foreground sm:size-8"
                    />
                  }
                >
                  <RotateCcw
                    className={cn("size-4", isResetting && "animate-spin")}
                  />
                </TooltipTrigger>
                <TooltipContent side="bottom">{resetLabel}</TooltipContent>
              </Tooltip>

              <Button
                type="button"
                variant="outline"
                size="icon"
                onClick={() => setMenuOpen((prev) => !prev)}
                aria-expanded={menuOpen}
                aria-controls="app-mobile-utilities"
                aria-label={menuOpen ? t.prod.nav.closeMenu : t.prod.nav.menu}
                className={cn(
                  "inline-flex size-10 shrink-0 rounded-[10px] p-0 text-muted-foreground hover:text-foreground sm:size-8 md:hidden",
                  menuOpen && "border-foreground/30 bg-muted text-foreground"
                )}
              >
                {menuOpen ? (
                  <X className="size-4" />
                ) : (
                  <Menu className="size-4" />
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

            {/* Collapsible utility tray on < md (keeps language switch, company chip, shortcuts accessible) */}
            {menuOpen && (
              <div
                id="app-mobile-utilities"
                className="order-4 col-span-3 mt-2.5 flex flex-wrap items-center justify-between gap-2 border-t border-border/70 pt-2.5 md:hidden"
              >
                <CompanyChip
                  name={t.brand.companyName}
                  className="max-w-full"
                />

                <div className="flex items-center gap-2">
                  <LanguageSwitch
                    lang={lang}
                    onChange={setLang}
                    ariaLabel={t.nav.langAriaLabel}
                  />

                  {onOpenShortcuts && (
                    <Button
                      type="button"
                      variant="outline"
                      size="icon"
                      onClick={() => {
                        setMenuOpen(false);
                        onOpenShortcuts();
                      }}
                      aria-label={t.nav.shortcutsTooltip}
                      title={t.nav.shortcutsTooltip}
                      className="size-8 shrink-0 rounded-[10px] p-0 text-muted-foreground hover:text-foreground"
                    >
                      <Keyboard className="size-4" />
                    </Button>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
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
