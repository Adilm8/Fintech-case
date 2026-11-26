"use client";

import type { CSSProperties } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Info,
  Loader2,
  OctagonX,
} from "lucide-react";
import { Toaster as Sonner, type ToasterProps } from "sonner";

function Toaster({ ...props }: ToasterProps) {
  return (
    <Sonner
      theme="light"
      position="top-right"
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
            "group toast rounded-2xl border border-border bg-card text-foreground shadow-[0_8px_24px_rgba(29,29,30,0.10)] font-sans",
          title: "text-sm font-semibold text-foreground",
          description: "text-xs text-muted-foreground leading-relaxed",
          actionButton:
            "bg-primary text-primary-foreground hover:bg-[var(--brand-hover)] rounded-lg text-xs font-medium",
          cancelButton:
            "bg-muted text-muted-foreground hover:text-foreground rounded-lg text-xs font-medium",
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
