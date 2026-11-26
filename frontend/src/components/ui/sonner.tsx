"use client";

import { useSyncExternalStore, type CSSProperties } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Info,
  Loader2,
  OctagonX,
} from "lucide-react";
import { Toaster as Sonner, type ToasterProps } from "sonner";

const MOBILE_MEDIA_QUERY = "(max-width: 767px)";

function subscribeMobileViewport(listener: () => void): () => void {
  if (typeof window === "undefined" || !window.matchMedia) {
    return () => {};
  }
  const mql = window.matchMedia(MOBILE_MEDIA_QUERY);
  mql.addEventListener("change", listener);
  return () => mql.removeEventListener("change", listener);
}

function getMobileViewportSnapshot(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) {
    return false;
  }
  return window.matchMedia(MOBILE_MEDIA_QUERY).matches;
}

function getServerMobileViewportSnapshot(): boolean {
  return false;
}

function Toaster({ position, ...props }: ToasterProps) {
  const isMobile = useSyncExternalStore(
    subscribeMobileViewport,
    getMobileViewportSnapshot,
    getServerMobileViewportSnapshot
  );

  const resolvedPosition = position ?? (isMobile ? "bottom-center" : "top-right");

  return (
    <Sonner
      theme="light"
      position={resolvedPosition}
      closeButton
      className="toaster group"
      icons={{
        success: <CheckCircle2 className="size-4 text-[#00AB75]" />,
        info: <Info className="size-4 text-sky-600" />,
        warning: <AlertTriangle className="size-4 text-amber-600" />,
        error: <OctagonX className="size-4 text-red-600" />,
        loading: <Loader2 className="size-4 animate-spin text-[#00AB75]" />,
      }}
      toastOptions={{
        classNames: {
          toast:
            "group toast rounded-[8px] border border-border bg-card text-foreground shadow-[var(--shadow-overlay)] font-sans",
          title: "text-sm font-semibold text-foreground",
          description: "text-xs text-muted-foreground leading-relaxed",
          actionButton:
            "bg-primary text-primary-foreground hover:bg-[var(--brand-hover)] rounded-[6px] text-xs font-medium",
          cancelButton:
            "bg-muted text-muted-foreground hover:text-foreground rounded-[6px] text-xs font-medium",
          closeButton:
            "border-border bg-card text-muted-foreground hover:bg-muted hover:text-foreground",
        },
      }}
      style={
        {
          "--normal-bg": "var(--card)",
          "--normal-text": "var(--foreground)",
          "--normal-border": "var(--border)",
          "--border-radius": "var(--radius)",
        } as CSSProperties
      }
      {...props}
    />
  );
}

export { Toaster };
