"use client";

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
          <DialogTitle>{t.shortcuts.title}</DialogTitle>
          <DialogDescription>{t.shortcuts.description}</DialogDescription>
        </DialogHeader>

        <div className="divide-y divide-border rounded-[6px] border border-border bg-card">
          {items.map((item) => (
            <div
              key={item.keyLabel}
              className="flex items-center justify-between gap-4 px-3 py-2 text-sm"
            >
              <span className="text-foreground">{item.description}</span>
              <kbd className="inline-flex min-w-7 shrink-0 items-center justify-center rounded-[4px] border border-border bg-muted px-1.5 py-0.5 font-mono text-xs font-medium text-foreground">
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
