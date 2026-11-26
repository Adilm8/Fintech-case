"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { ProdHeader } from "@/components/prod/ProdHeader";
import {
  Alert,
  AlertAction,
  AlertDescription,
  AlertTitle,
} from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useT } from "@/i18n";
import { getApprovals } from "@/lib/prod/api";
import {
  defaultHomeForRole,
  SessionProvider,
  useSession,
} from "@/lib/prod/session";

const DEMO_PREFIXES = ["/check", "/approvals", "/attack", "/metrics"] as const;

function isDemoPath(pathname: string): boolean {
  if (pathname === "/") return true;
  return DEMO_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)
  );
}

export const PROD_APPROVALS_UPDATED_EVENT = "prod:approvals-updated";

export function notifyProdApprovalsUpdated(): void {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(PROD_APPROVALS_UPDATED_EVENT));
  }
}

function ProdShellInner({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { t, lang } = useT();
  const { session, isLoading, networkError, refreshSession, logout } =
    useSession();

  const [pendingApprovalsCount, setPendingApprovalsCount] = useState(0);

  const isLoginRoute = pathname === "/login";
  const isDemoRoute = isDemoPath(pathname);

  useEffect(() => {
    if (isDemoRoute) {
      if (!isLoading && !session) {
        router.replace("/login");
      } else {
        router.replace("/payments");
      }
      return;
    }

    if (isLoading) return;

    if (!session && !isLoginRoute) {
      router.replace("/login");
      return;
    }

    if (session && isLoginRoute) {
      router.replace(defaultHomeForRole(session.user.role));
    }
  }, [isDemoRoute, isLoading, isLoginRoute, router, session]);

  const isDirector = session?.user.role === "director";

  const fetchPendingCount = useCallback(async () => {
    if (!isDirector) return;
    try {
      const list = await getApprovals({ status: "pending" }, lang, {
        suppressAuthRedirect: true,
      });
      setPendingApprovalsCount(list.length);
    } catch {
      // Non-blocking badge fetch; main screens surface errors directly.
    }
  }, [isDirector, lang]);

  useEffect(() => {
    if (!isDirector) return;
    let active = true;
    getApprovals({ status: "pending" }, lang, { suppressAuthRedirect: true })
      .then((list) => {
        if (active) setPendingApprovalsCount(list.length);
      })
      .catch(() => {
        // Non-blocking badge fetch.
      });
    return () => {
      active = false;
    };
  }, [isDirector, lang, pathname]);

  useEffect(() => {
    if (!isDirector) return;
    const onUpdated = () => {
      void fetchPendingCount();
    };
    window.addEventListener(PROD_APPROVALS_UPDATED_EVENT, onUpdated);
    const interval = window.setInterval(onUpdated, 30000);
    return () => {
      window.removeEventListener(PROD_APPROVALS_UPDATED_EVENT, onUpdated);
      window.clearInterval(interval);
    };
  }, [fetchPendingCount, isDirector]);

  const effectivePendingCount = isDirector ? pendingApprovalsCount : 0;

  // Never render demo pages inside ProdShell (they require AppShell).
  if (isDemoRoute) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background p-6">
        <div className="w-full max-w-md space-y-3">
          <Skeleton className="h-8 w-48 mx-auto rounded-lg" />
          <Skeleton className="h-24 w-full rounded-xl" />
        </div>
      </div>
    );
  }

  if (isLoginRoute) {
    if (session) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-background p-6">
          <Skeleton className="h-24 w-64 rounded-xl" />
        </div>
      );
    }
    return <>{children}</>;
  }

  if (isLoading) {
    return (
      <div className="min-h-screen flex flex-col bg-background">
        <div className="border-b border-border bg-card">
          <div className="mx-auto flex w-full max-w-[1248px] items-center justify-between px-4 py-3.5 sm:px-6">
            <div className="flex items-center gap-3">
              <Skeleton className="size-9 rounded-xl" />
              <Skeleton className="h-5 w-36" />
            </div>
            <Skeleton className="h-9 w-40 rounded-xl" />
          </div>
        </div>
        <main className="mx-auto w-full max-w-[1248px] flex-1 px-4 py-6 space-y-5 sm:px-6">
          <Skeleton className="h-8 w-56" />
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-28 w-full rounded-xl" />
            ))}
          </div>
          <Skeleton className="h-64 w-full rounded-xl" />
        </main>
      </div>
    );
  }

  if (!session) {
    if (networkError) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-background p-4">
          <Alert
            variant="destructive"
            className="max-w-lg rounded-2xl border-red-300 bg-red-50/90 px-4 py-4"
          >
            <AlertTriangle className="size-4" />
            <AlertTitle>{t.common.serverErrorTitle}</AlertTitle>
            <AlertDescription className="break-words">
              {networkError}
            </AlertDescription>
            <AlertAction className="static col-span-full mt-3">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => void refreshSession()}
                className="min-h-11 w-full gap-1.5 border-red-300 bg-white text-red-900 hover:bg-red-50 sm:min-h-8 sm:w-auto"
              >
                <RefreshCw className="size-3.5" />
                <span>{t.common.retry}</span>
              </Button>
            </AlertAction>
          </Alert>
        </div>
      );
    }
    return null;
  }

  return (
    <div className="min-h-screen flex flex-col bg-background overflow-x-clip">
      <ProdHeader
        session={session}
        pendingApprovalsCount={effectivePendingCount}
        onLogout={logout}
      />

      <main className="mx-auto w-full max-w-[1248px] flex-1 px-4 py-4 space-y-5 sm:px-6 sm:py-6 sm:space-y-6">
        {children}
      </main>
    </div>
  );
}

export function ProdShell({ children }: { children: ReactNode }) {
  return (
    <SessionProvider>
      <ProdShellInner>{children}</ProdShellInner>
    </SessionProvider>
  );
}
