"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  AlertTriangle,
  Bell,
  CheckCheck,
  CheckCircle2,
  ClipboardCheck,
  Loader2,
  Settings,
  ShieldAlert,
  XCircle,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useT } from "@/i18n";
import { formatDateForLang } from "@/lib/format";
import {
  getNotifications,
  getProdErrorMessage,
  markNotificationsRead,
} from "@/lib/prod/api";
import type { NotificationItem, Role } from "@/lib/prod/types";
import { notify } from "@/lib/toast";
import { cn } from "cn";

export const PROD_NOTIFICATIONS_UPDATED_EVENT = "prod:notifications-updated";

export function notifyProdNotificationsUpdated(): void {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(PROD_NOTIFICATIONS_UPDATED_EVENT));
  }
}

interface NotificationBellProps {
  role: Role;
}

function formatTime(iso: string, lang: "ru" | "kk" | "en"): string {
  const datePart = formatDateForLang(iso, lang);
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return datePart;
  const hh = String(parsed.getHours()).padStart(2, "0");
  const mm = String(parsed.getMinutes()).padStart(2, "0");
  return `${datePart} ${hh}:${mm}`;
}

function kindIcon(kind: NotificationItem["kind"]) {
  switch (kind) {
    case "approval_pending":
      return {
        Icon: ClipboardCheck,
        cls: "bg-amber-50 text-amber-700 border-amber-200",
      };
    case "approval_approved":
      return {
        Icon: CheckCircle2,
        cls: "bg-[#E8F8F2] text-[#006B49] border-[#00AB75]/30",
      };
    case "approval_rejected":
      return {
        Icon: XCircle,
        cls: "bg-red-50 text-red-700 border-red-200",
      };
    case "sign_denied":
      return {
        Icon: ShieldAlert,
        cls: "bg-red-50 text-red-700 border-red-200",
      };
    default:
      return {
        Icon: AlertTriangle,
        cls: "bg-muted text-muted-foreground border-border",
      };
  }
}

export function NotificationBell({ role }: NotificationBellProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { t, lang, interpolate } = useT();

  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [isMarkingAll, setIsMarkingAll] = useState(false);

  const containerRef = useRef<HTMLDivElement>(null);

  const loadNotifications = useCallback(
    async (silent = true) => {
      if (!silent) setIsLoading(true);
      try {
        const res = await getNotifications({ limit: 30 }, lang, {
          suppressAuthRedirect: true,
        });
        setItems(res.items);
        setUnreadCount(res.unread_count);
      } catch {
        // Non-blocking background poll.
      } finally {
        if (!silent) setIsLoading(false);
      }
    },
    [lang]
  );

  useEffect(() => {
    let active = true;
    getNotifications({ limit: 30 }, lang, { suppressAuthRedirect: true })
      .then((res) => {
        if (!active) return;
        setItems(res.items);
        setUnreadCount(res.unread_count);
      })
      .catch(() => {
        // Non-blocking background poll.
      });
    return () => {
      active = false;
    };
  }, [lang, pathname]);

  useEffect(() => {
    const onRefresh = () => {
      void loadNotifications(true);
    };
    window.addEventListener("prod:approvals-updated", onRefresh);
    window.addEventListener(PROD_NOTIFICATIONS_UPDATED_EVENT, onRefresh);
    const interval = window.setInterval(onRefresh, 30000);
    return () => {
      window.removeEventListener("prod:approvals-updated", onRefresh);
      window.removeEventListener(PROD_NOTIFICATIONS_UPDATED_EVENT, onRefresh);
      window.clearInterval(interval);
    };
  }, [loadNotifications]);

  useEffect(() => {
    if (!open) return;
    const handlePointerDown = (event: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setOpen(false);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  const handleToggle = () => {
    const next = !open;
    setOpen(next);
    if (next) {
      void loadNotifications(false);
    }
  };

  const handleMarkAllRead = async () => {
    if (isMarkingAll || unreadCount === 0) return;
    setIsMarkingAll(true);
    try {
      const res = await markNotificationsRead(undefined, lang);
      setUnreadCount(res.unread_count);
      setItems((prev) => prev.map((it) => ({ ...it, read: true })));
    } catch (err) {
      notify.error(t.common.serverErrorTitle, getProdErrorMessage(err));
    } finally {
      setIsMarkingAll(false);
    }
  };

  const handleOpenItem = async (item: NotificationItem) => {
    setOpen(false);
    if (!item.read) {
      setItems((prev) =>
        prev.map((it) => (it.id === item.id ? { ...it, read: true } : it))
      );
      setUnreadCount((c) => Math.max(0, c - 1));
      try {
        const res = await markNotificationsRead([item.id], lang);
        setUnreadCount(res.unread_count);
      } catch {
        // Ignore single mark failure; next poll reconciles.
      }
    }
    if (item.link) {
      router.push(item.link);
    }
  };

  const badgeLabel = unreadCount > 99 ? "99+" : String(unreadCount);

  return (
    <div ref={containerRef} className="relative">
      <Button
        type="button"
        variant="outline"
        size="icon"
        onClick={handleToggle}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label={t.prod.notifications.ariaLabel}
        title={t.prod.notifications.title}
        className={cn(
          "relative size-11 shrink-0 p-0 text-muted-foreground hover:text-foreground sm:size-9",
          open && "border-primary/50 bg-accent/60 text-foreground"
        )}
      >
        <Bell className="size-4" />
        {unreadCount > 0 && (
          <span
            aria-label={interpolate(t.prod.notifications.unreadBadge, {
              count: unreadCount,
            })}
            className="absolute -top-1 -right-1 flex min-h-[18px] min-w-[18px] items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-bold leading-none text-white tabular-nums shadow-xs ring-2 ring-card"
          >
            {badgeLabel}
          </span>
        )}
      </Button>

      {open && (
        <div
          role="dialog"
          aria-label={t.prod.notifications.title}
          className="absolute -right-[50px] top-full z-50 mt-2 w-[calc(100vw-2rem)] max-w-[370px] overflow-hidden rounded-2xl border border-border bg-card shadow-xl sm:right-0 sm:w-[370px]"
        >
          <div className="flex items-center justify-between gap-2 border-b border-border bg-muted/35 px-4 py-3">
            <div className="flex min-w-0 items-center gap-2">
              <span className="text-sm font-semibold text-foreground">
                {t.prod.notifications.title}
              </span>
              {unreadCount > 0 && (
                <Badge
                  variant="secondary"
                  className="h-auto px-1.5 py-0.5 text-[11px] font-semibold tabular-nums"
                >
                  {unreadCount}
                </Badge>
              )}
            </div>

            {unreadCount > 0 && (
              <button
                type="button"
                onClick={() => void handleMarkAllRead()}
                disabled={isMarkingAll}
                className="inline-flex cursor-pointer items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-[var(--brand-text)] transition-colors hover:bg-accent disabled:opacity-60"
              >
                {isMarkingAll ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <CheckCheck className="size-3.5" />
                )}
                <span>
                  {isMarkingAll
                    ? t.prod.notifications.markingRead
                    : t.prod.notifications.markAllRead}
                </span>
              </button>
            )}
          </div>

          <div className="max-h-[380px] overflow-y-auto divide-y divide-border">
            {isLoading && items.length === 0 ? (
              <div className="flex items-center justify-center py-10 text-muted-foreground">
                <Loader2 className="size-5 animate-spin" />
              </div>
            ) : items.length === 0 ? (
              <div className="px-4 py-10 text-center space-y-1.5">
                <div className="mx-auto flex size-10 items-center justify-center rounded-xl bg-muted text-muted-foreground">
                  <Bell className="size-5" />
                </div>
                <div className="text-sm font-semibold text-foreground">
                  {t.prod.notifications.emptyTitle}
                </div>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  {t.prod.notifications.emptyDescription}
                </p>
              </div>
            ) : (
              items.map((item) => {
                const { Icon, cls } = kindIcon(item.kind);
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => void handleOpenItem(item)}
                    className={cn(
                      "flex w-full cursor-pointer items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/55 focus-visible:bg-accent/50 focus-visible:outline-none",
                      !item.read && "bg-accent/35"
                    )}
                  >
                    <div
                      className={cn(
                        "mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-xl border",
                        cls
                      )}
                    >
                      <Icon className="size-4" />
                    </div>
                    <div className="min-w-0 flex-1 space-y-1">
                      <div className="flex items-start justify-between gap-2">
                        <span className="text-xs font-semibold text-foreground leading-snug">
                          {item.title}
                        </span>
                        {!item.read && (
                          <span
                            aria-hidden="true"
                            className="mt-1 size-2 shrink-0 rounded-full bg-primary"
                          />
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground leading-snug break-words">
                        {item.message}
                      </p>
                      <div className="text-[11px] text-muted-foreground/80 tabular-nums">
                        {formatTime(item.created_at, lang)}
                      </div>
                    </div>
                  </button>
                );
              })
            )}
          </div>

          {role === "director" && (
            <div className="border-t border-border bg-muted/25 px-4 py-2.5">
              <Link
                href="/settings"
                onClick={() => setOpen(false)}
                className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--brand-text)] hover:underline"
              >
                <Settings className="size-3.5" />
                <span>{t.prod.notifications.settingsLink}</span>
              </Link>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
