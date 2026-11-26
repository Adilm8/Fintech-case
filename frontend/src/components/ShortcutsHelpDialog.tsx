"use client";

import { Keyboard } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useT } from "@/i18n";

interface ShortcutsHelpDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ShortcutsHelpDialog({
  open,
  onOpenChange,
}: ShortcutsHelpDialogProps) {
  const { t } = useT();

  const items = [
    { keyLabel: "/", description: t.shortcuts.searchDesc },
    { keyLabel: "N", description: t.shortcuts.newPaymentDesc },
    { keyLabel: "Esc", description: t.shortcuts.closeDialogDesc },
    { keyLabel: "?", description: t.shortcuts.helpDesc },
  ];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-accent text-[var(--brand-text)]">
              <Keyboard className="size-4" />
            </div>
            <DialogTitle>{t.shortcuts.title}</DialogTitle>
          </div>
          <DialogDescription>{t.shortcuts.description}</DialogDescription>
        </DialogHeader>

        <div className="divide-y divide-border rounded-xl border border-border bg-background/60">
          {items.map((item) => (
            <div
              key={item.keyLabel}
              className="flex items-center justify-between gap-4 px-3.5 py-2.5 text-sm"
            >
              <span className="text-foreground">{item.description}</span>
              <kbd className="inline-flex min-w-8 shrink-0 items-center justify-center rounded-md border border-border bg-card px-2 py-1 font-mono text-xs font-semibold text-foreground shadow-xs">
                {item.keyLabel}
              </kbd>
            </div>
          ))}
        </div>

        <p className="text-xs text-muted-foreground">{t.shortcuts.note}</p>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            className="min-h-11 w-full sm:min-h-9 sm:w-auto"
          >
            {t.common.close}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
