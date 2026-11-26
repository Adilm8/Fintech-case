"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Bell, Loader2 } from "lucide-react";
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

function kindDotClass(kind: NotificationItem["kind"]): string {
  switch (kind) {
    case "approval_pending":
      return "ui-dot-warn";
    case "approval_approved":
      return "ui-dot-ok";
    case "approval_rejected":
    case "sign_denied":
      return "ui-dot-danger";
    default:
      return "ui-dot-neutral";
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
          "relative size-11 shrink-0 p-0 text-muted-foreground hover:text-foreground sm:size-8",
          open && "border-foreground bg-muted text-foreground"
        )}
      >
        <Bell className="size-4" />
        {unreadCount > 0 && (
          <span
            aria-label={interpolate(t.prod.notifications.unreadBadge, {
              count: unreadCount,
            })}
            className="absolute -top-1 -right-1 flex min-h-[16px] min-w-[16px] items-center justify-center rounded-full bg-[var(--status-danger)] px-1 text-[10px] font-semibold leading-none text-white tabular-nums ring-2 ring-card"
          >
            {badgeLabel}
          </span>
        )}
      </Button>

      {open && (
        <div
          role="dialog"
          aria-label={t.prod.notifications.title}
          className="absolute -right-[50px] top-full z-50 mt-2 w-[calc(100vw-2rem)] max-w-[370px] overflow-hidden rounded-[8px] border border-border bg-card shadow-[var(--shadow-overlay)] sm:right-0 sm:w-[370px]"
        >
          <div className="flex items-center justify-between gap-2 border-b border-border bg-muted/40 px-4 py-2.5">
            <div className="flex min-w-0 items-center gap-2">
              <span className="text-sm font-semibold text-foreground">
                {t.prod.notifications.title}
              </span>
              {unreadCount > 0 && (
                <span className="ui-tag tabular-nums">{unreadCount}</span>
              )}
            </div>

            {unreadCount > 0 && (
              <button
                type="button"
                onClick={() => void handleMarkAllRead()}
                disabled={isMarkingAll}
                className="inline-flex cursor-pointer items-center gap-1 rounded-[4px] px-2 py-1 text-xs font-medium text-[var(--brand-text)] transition-colors hover:bg-muted disabled:opacity-60"
              >
                {isMarkingAll && <Loader2 className="size-3.5 animate-spin" />}
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
              <div className="flex items-center justify-center py-8 text-muted-foreground">
                <Loader2 className="size-4 animate-spin" />
              </div>
            ) : items.length === 0 ? (
              <div className="ui-empty">
                <div className="ui-empty-title">
                  {t.prod.notifications.emptyTitle}
                </div>
                <p className="ui-empty-desc">
                  {t.prod.notifications.emptyDescription}
                </p>
              </div>
            ) : (
              items.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => void handleOpenItem(item)}
                  className={cn(
                    "flex w-full cursor-pointer items-start gap-2.5 px-4 py-3 text-left transition-colors hover:bg-muted/60 focus-visible:bg-muted/70 focus-visible:outline-none",
                    !item.read && "bg-muted/50"
                  )}
                >
                  <span
                    aria-hidden="true"
                    className={cn(
                      "ui-status-dot mt-1.5",
                      kindDotClass(item.kind)
                    )}
                  />
                  <div className="min-w-0 flex-1 space-y-1">
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-xs font-semibold text-foreground leading-snug">
                        {item.title}
                      </span>
                      {!item.read && (
                        <span
                          aria-hidden="true"
                          className="mt-1 size-1.5 shrink-0 rounded-full bg-primary"
                        />
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground leading-snug break-words">
                      {item.message}
                    </p>
                    <div className="text-[11px] text-muted-foreground tabular-nums">
                      {formatTime(item.created_at, lang)}
                    </div>
                  </div>
                </button>
              ))
            )}
          </div>

          {role === "director" && (
            <div className="border-t border-border bg-muted/30 px-4 py-2.5">
              <Link
                href="/settings"
                onClick={() => setOpen(false)}
                className="text-xs font-medium text-[var(--brand-text)] hover:underline"
              >
                {t.prod.notifications.settingsLink}
              </Link>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
