"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "cn";
import { useT } from "@/i18n";
import {
  ApiError,
  getMe,
  getProdErrorMessage,
  isProdNetworkError,
  logout as apiLogout,
  setUnauthorizedHandler,
} from "@/lib/prod/api";
import type { Role, Session } from "@/lib/prod/types";

export function defaultHomeForRole(role: Role): string {
  if (role === "director") return "/director";
  return "/payments";
}

interface SessionContextValue {
  session: Session | null;
  isLoading: boolean;
  networkError: string | null;
  setSession: (session: Session | null) => void;
  refreshSession: () => Promise<Session | null>;
  logout: () => Promise<void>;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { lang } = useT();

  const [session, setSessionState] = useState<Session | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [networkError, setNetworkError] = useState<string | null>(null);

  const setSession = useCallback((next: Session | null) => {
    setSessionState(next);
    if (next) {
      setNetworkError(null);
    }
  }, []);

  const refreshSession = useCallback(async (): Promise<Session | null> => {
    try {
      const me = await getMe(lang, { suppressAuthRedirect: true });
      setSessionState(me);
      setNetworkError(null);
      return me;
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setSessionState(null);
        setNetworkError(null);
        return null;
      }
      if (isProdNetworkError(err)) {
        setNetworkError(getProdErrorMessage(err));
      }
      return null;
    }
  }, [lang]);

  useEffect(() => {
    let active = true;
    getMe(lang, { suppressAuthRedirect: true })
      .then((me) => {
        if (!active) return;
        setSessionState(me);
        setNetworkError(null);
      })
      .catch((err) => {
        if (!active) return;
        if (err instanceof ApiError && err.status === 401) {
          setSessionState(null);
          setNetworkError(null);
        } else if (isProdNetworkError(err)) {
          setNetworkError(getProdErrorMessage(err));
        }
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });

    return () => {
      active = false;
    };
    // Initial session probe runs once on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setSessionState(null);
      if (pathname !== "/login") {
        router.replace("/login");
      }
    });
    return () => {
      setUnauthorizedHandler(null);
    };
  }, [pathname, router]);

  const logout = useCallback(async () => {
    try {
      await apiLogout(lang);
    } catch {
      // Ignore logout errors; always clear local session state.
    } finally {
      setSessionState(null);
      router.replace("/login");
    }
  }, [lang, router]);

  const value = useMemo<SessionContextValue>(
    () => ({
      session,
      isLoading,
      networkError,
      setSession,
      refreshSession,
      logout,
    }),
    [session, isLoading, networkError, setSession, refreshSession, logout]
  );

  return (
    <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
  );
}

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) {
    throw new Error("useSession must be used inside SessionProvider");
  }
  return ctx;
}

interface RequireRoleProps {
  roles: readonly Role[];
  children: ReactNode;
}

export function RequireRole({ roles, children }: RequireRoleProps) {
  const { session, isLoading } = useSession();
  const { t } = useT();

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-7 w-56 rounded-[6px]" />
        <Skeleton className="h-40 w-full rounded-[8px]" />
      </div>
    );
  }

  if (!session) {
    return null;
  }

  if (!roles.includes(session.user.role)) {
    const homeHref = defaultHomeForRole(session.user.role);
    return (
      <div className="ui-panel max-w-lg">
        <div className="ui-empty">
          <h1 className="ui-empty-title">{t.prod.access.deniedTitle}</h1>
          <p className="ui-empty-desc">{t.prod.access.deniedDescription}</p>
          <Link
            href={homeHref}
            className={cn(
              buttonVariants({ variant: "outline", size: "sm" }),
              "mt-2 min-h-10 sm:min-h-8"
            )}
          >
            {t.prod.access.backHome}
          </Link>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
