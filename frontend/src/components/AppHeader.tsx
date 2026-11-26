"use client";

import { Building2, RotateCcw, ShieldCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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

  return (
    <header className="sticky top-0 z-30 border-b border-border bg-card/95 backdrop-blur supports-[backdrop-filter]:bg-card/85">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-6 py-3.5">
        <div className="flex items-center gap-5">
          <button
            type="button"
            onClick={onLogoClick}
            className="flex items-center gap-2.5 text-left transition-opacity hover:opacity-85 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-md"
          >
            <div className="flex size-9 items-center justify-center rounded-lg bg-[var(--brand)] text-[var(--brand-foreground)] shadow-xs">
              <ShieldCheck className="size-5" />
            </div>
            <div>
              <div className="text-base font-semibold tracking-tight text-foreground leading-tight">
                BCC Business Shield
              </div>
              <div className="text-xs text-muted-foreground">
                Защита платежей перед подписанием
              </div>
            </div>
          </button>

          <div className="hidden h-7 w-px bg-border sm:block" />

          <div className="hidden items-center gap-2 rounded-lg border border-border bg-muted/50 px-3 py-1.5 text-sm sm:flex">
            <Building2 className="size-4 text-muted-foreground" />
            <span className="font-medium text-foreground">
              ТОО &quot;ТехноСтрой Астана&quot;
            </span>
          </div>
        </div>

        <div className="flex items-center gap-3.5">
          <div
            className="inline-flex items-center rounded-lg border border-border bg-muted p-1 gap-1"
            role="group"
            aria-label="Переключатель роли"
          >
            <button
              type="button"
              aria-pressed={isAccountant}
              onClick={() => onRoleChange("accountant")}
              className={cn(
                "inline-flex items-center justify-center rounded-md px-3.5 py-1.5 text-sm transition-all cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
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
                "inline-flex items-center justify-center gap-1.5 rounded-md px-3.5 py-1.5 text-sm transition-all cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
                isDirector
                  ? "bg-[var(--brand)] text-[var(--brand-foreground)] font-semibold shadow-xs"
                  : "text-muted-foreground font-medium hover:bg-background/70 hover:text-foreground"
              )}
            >
              <span>Директор</span>
              <Badge
                variant={pendingCount > 0 ? "default" : "secondary"}
                className={cn(
                  "h-5 min-w-5 px-1.5 text-xs tabular-nums",
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

          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onResetDemo}
            disabled={isResetting}
            className="gap-1.5 text-muted-foreground hover:text-foreground"
          >
            <RotateCcw
              className={cn("size-3.5", isResetting && "animate-spin")}
            />
            <span>{isResetting ? "Сброс..." : "Сбросить демо"}</span>
          </Button>
        </div>
      </div>
    </header>
  );
}
