"use client";

import { Building2, RotateCcw, ShieldCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { UserRole } from "@/lib/types";
import { cn } from "cn";

interface AppHeaderProps {
  role: UserRole;
  onRoleChange: (role: UserRole) => void;
  pendingCount: number;
  onResetDemo: () => void;
  isResetting: boolean;
  onLogoClick?: () => void;
}

export function AppHeader({
  role,
  onRoleChange,
  pendingCount,
  onResetDemo,
  isResetting,
  onLogoClick,
}: AppHeaderProps) {
  const isAccountant = role === "accountant";
  const isDirector = role === "director";
  const resetLabel = isResetting ? "Сброс..." : "Сбросить демо";

  return (
    <header className="relative z-30 border-b border-border bg-card/95 backdrop-blur supports-[backdrop-filter]:bg-card/85 md:sticky md:top-0">
      <div className="mx-auto grid w-full max-w-[1248px] grid-cols-[minmax(0,1fr)_auto] items-center gap-x-2.5 gap-y-2.5 px-4 py-3 sm:grid-cols-[auto_minmax(0,1fr)_auto] sm:gap-x-4 sm:gap-y-3 sm:px-6 lg:flex lg:flex-nowrap lg:items-center lg:gap-4">
        <button
          type="button"
          onClick={onLogoClick}
          className="col-start-1 row-start-1 flex min-h-11 min-w-0 items-center gap-2.5 rounded-md text-left transition-opacity hover:opacity-85 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring lg:shrink-0"
        >
          <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-[var(--brand)] text-[var(--brand-foreground)] shadow-xs">
            <ShieldCheck className="size-5" />
          </div>
          <div className="min-w-0">
            <div className="text-sm font-semibold tracking-tight text-foreground leading-tight sm:text-base">
              BCC Business Shield
            </div>
            <div className="text-xs leading-snug text-muted-foreground">
              Защита платежей перед подписанием
            </div>
          </div>
        </button>

        <div className="col-span-2 row-start-2 flex min-w-0 items-center sm:col-span-2 sm:col-start-2 sm:row-start-1 sm:border-l sm:border-border sm:pl-4 lg:mr-auto">
          <div className="inline-flex max-w-full min-w-0 items-center gap-2 rounded-lg border border-border bg-muted/50 px-2.5 py-1 text-xs sm:px-3 sm:py-1.5 sm:text-sm">
            <Building2 className="size-3.5 shrink-0 text-muted-foreground sm:size-4" />
            <span className="truncate font-medium text-foreground">
              ТОО &quot;ТехноСтрой Астана&quot;
            </span>
          </div>
        </div>

        <div
          className="col-span-2 row-start-3 grid w-full grid-cols-2 items-center gap-1 rounded-lg border border-border bg-muted p-1 sm:col-span-2 sm:col-start-1 sm:row-start-2 sm:inline-flex sm:w-fit lg:shrink-0"
          role="group"
          aria-label="Переключатель роли"
        >
          <button
            type="button"
            aria-pressed={isAccountant}
            onClick={() => onRoleChange("accountant")}
            className={cn(
              "inline-flex min-h-11 items-center justify-center rounded-md px-3 py-1.5 text-sm transition-all cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 sm:min-h-9 sm:px-3.5",
              isAccountant
                ? "bg-[var(--brand)] text-[var(--brand-foreground)] font-semibold shadow-xs"
                : "text-muted-foreground font-medium hover:bg-background/70 hover:text-foreground"
            )}
          >
            Бухгалтер
          </button>

          <button
            type="button"
            aria-pressed={isDirector}
            onClick={() => onRoleChange("director")}
            className={cn(
              "inline-flex min-h-11 items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-sm transition-all cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 sm:min-h-9 sm:px-3.5",
              isDirector
                ? "bg-[var(--brand)] text-[var(--brand-foreground)] font-semibold shadow-xs"
                : "text-muted-foreground font-medium hover:bg-background/70 hover:text-foreground"
            )}
          >
            <span>Директор</span>
            <Badge
              variant={pendingCount > 0 ? "default" : "secondary"}
              className={cn(
                "h-auto min-h-5 min-w-5 px-1.5 py-0.5 text-xs tabular-nums",
                pendingCount > 0
                  ? "bg-amber-500 text-white border-transparent hover:bg-amber-500"
                  : isDirector
                    ? "bg-white/20 text-white border-transparent"
                    : "bg-background text-muted-foreground border-border"
              )}
            >
              {pendingCount}
            </Badge>
          </button>
        </div>

        <div className="col-start-2 row-start-1 justify-self-end sm:col-start-3 sm:row-start-2 lg:shrink-0">
          <Tooltip>
            <TooltipTrigger
              render={
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={onResetDemo}
                  disabled={isResetting}
                  aria-label={resetLabel}
                  title={resetLabel}
                  className="min-h-11 min-w-11 px-0 text-muted-foreground hover:text-foreground sm:min-h-9 sm:min-w-0 sm:gap-1.5 sm:px-3"
                />
              }
            >
              <RotateCcw
                className={cn(
                  "size-4 sm:size-3.5",
                  isResetting && "animate-spin"
                )}
              />
              <span className="hidden sm:inline">{resetLabel}</span>
            </TooltipTrigger>
            <TooltipContent side="bottom" className="sm:hidden">
              {resetLabel}
            </TooltipContent>
          </Tooltip>
        </div>
      </div>
    </header>
  );
}
