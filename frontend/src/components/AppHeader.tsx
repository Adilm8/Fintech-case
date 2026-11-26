"use client";

import { Building2, RotateCcw, ShieldCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
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

        <div className="flex items-center gap-4">
          <div
            className="flex items-center gap-2.5 rounded-lg border border-border bg-background px-3 py-1.5"
            role="group"
            aria-label="Переключатель роли"
          >
            <button
              type="button"
              onClick={() => onRoleChange("accountant")}
              className={cn(
                "text-sm transition-colors cursor-pointer",
                !isDirector
                  ? "font-semibold text-foreground"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              Бухгалтер
            </button>

            <Switch
              aria-label="Переключить роль между Бухгалтер и Директор"
              checked={isDirector}
              onCheckedChange={(checked) =>
                onRoleChange(checked ? "director" : "accountant")
              }
            />

            <button
              type="button"
              onClick={() => onRoleChange("director")}
              className={cn(
                "flex items-center gap-1.5 text-sm transition-colors cursor-pointer",
                isDirector
                  ? "font-semibold text-foreground"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              <span>Директор</span>
              <Badge
                variant={pendingCount > 0 ? "default" : "secondary"}
                className={cn(
                  "h-5 min-w-5 px-1.5 text-xs tabular-nums",
                  pendingCount > 0 &&
                    "bg-amber-500 text-white hover:bg-amber-600"
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
