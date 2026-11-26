"use client";

import { useEffect, useState, type FormEvent } from "react";
import {
  AlertCircle,
  Bell,
  Loader2,
  Save,
  Settings,
  ShieldAlert,
} from "lucide-react";
import { notifyProdNotificationsUpdated } from "@/components/prod/NotificationBell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useT } from "@/i18n";
import {
  extractFieldErrors,
  getCompanySettings,
  getProdErrorMessage,
  updateCompanySettings,
} from "@/lib/prod/api";
import { RequireRole } from "@/lib/prod/session";
import type { NotifyOn } from "@/lib/prod/types";
import { notify } from "@/lib/toast";
import { cn } from "cn";

function SettingsPageContent() {
  const { t, lang, formatMoney, formatDate, interpolate } = useT();

  const fetchKey = lang;
  const [loadState, setLoadState] = useState<{
    key: string;
    error: string | null;
  } | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const [notifyOn, setNotifyOn] = useState<NotifyOn>("red_yellow");
  const [thresholdEnabled, setThresholdEnabled] = useState(false);
  const [thresholdInput, setThresholdInput] = useState("");
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getCompanySettings(lang, { signal: controller.signal })
      .then((data) => {
        setNotifyOn(data.notify_on);
        if (data.approval_threshold_kzt !== null) {
          setThresholdEnabled(true);
          setThresholdInput(String(data.approval_threshold_kzt));
        } else {
          setThresholdEnabled(false);
          setThresholdInput("");
        }
        setUpdatedAt(data.updated_at);
        setLoadState({ key: fetchKey, error: null });
      })
      .catch((err) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setLoadState({ key: fetchKey, error: getProdErrorMessage(err) });
      });
    return () => controller.abort();
  }, [fetchKey, lang]);

  const loadError = loadState?.error ?? null;
  const isLoading = loadState === null || loadState.key !== fetchKey;

  const parsedThreshold = (() => {
    const normalized = thresholdInput.replace(/\s+/g, "").replace(",", ".");
    if (!normalized) return null;
    const num = Number(normalized);
    if (!Number.isFinite(num) || num <= 0) return NaN;
    return num;
  })();

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSaveError(null);

    let thresholdPayload: number | null = null;
    if (thresholdEnabled) {
      if (parsedThreshold === null || Number.isNaN(parsedThreshold)) {
        setSaveError(t.prod.settings.thresholdInvalidError);
        return;
      }
      thresholdPayload = parsedThreshold;
    }

    setIsSaving(true);
    try {
      const updated = await updateCompanySettings(
        {
          notify_on: notifyOn,
          approval_threshold_kzt: thresholdPayload,
        },
        lang
      );
      setNotifyOn(updated.notify_on);
      if (updated.approval_threshold_kzt !== null) {
        setThresholdEnabled(true);
        setThresholdInput(String(updated.approval_threshold_kzt));
      } else {
        setThresholdEnabled(false);
        setThresholdInput("");
      }
      setUpdatedAt(updated.updated_at);
      notifyProdNotificationsUpdated();
      notify.success(t.prod.settings.savedToast);
    } catch (err) {
      const fieldErrors = extractFieldErrors(err);
      setSaveError(
        fieldErrors.approval_threshold_kzt ||
          fieldErrors.notify_on ||
          getProdErrorMessage(err)
      );
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="space-y-5 sm:space-y-6">
      <div className="min-w-0">
        <div className="flex items-center gap-2.5">
          <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-accent text-[var(--brand-text)]">
            <Settings className="size-5" />
          </div>
          <h1 className="text-xl font-semibold tracking-tight text-foreground sm:text-2xl">
            {t.prod.settings.title}
          </h1>
        </div>
        <p className="mt-1.5 text-sm text-muted-foreground">
          {t.prod.settings.subtitle}
        </p>
      </div>

      {loadError && (
        <Alert
          variant="destructive"
          className="rounded-2xl border-red-300 bg-red-50/90"
        >
          <AlertCircle className="size-4" />
          <AlertTitle>{t.common.serverErrorTitle}</AlertTitle>
          <AlertDescription className="break-words">{loadError}</AlertDescription>
        </Alert>
      )}

      {isLoading ? (
        <div className="space-y-4">
          <Skeleton className="h-56 w-full rounded-2xl" />
          <Skeleton className="h-56 w-full rounded-2xl" />
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-5">
          {saveError && (
            <Alert
              variant="destructive"
              className="rounded-2xl border-red-300 bg-red-50/90"
            >
              <AlertCircle className="size-4" />
              <AlertDescription className="break-words">
                {saveError}
              </AlertDescription>
            </Alert>
          )}

          <div className="grid grid-cols-1 items-start gap-5 lg:grid-cols-2">
            {/* Notification mode card */}
            <Card className="min-w-0">
              <CardHeader className="border-b border-border pb-4">
                <CardTitle className="flex items-center gap-2 text-base font-semibold">
                  <Bell className="size-4 text-muted-foreground" />
                  <span>{t.prod.settings.notifyCardTitle}</span>
                </CardTitle>
                <CardDescription>
                  {t.prod.settings.notifyCardDescription}
                </CardDescription>
              </CardHeader>

              <CardContent className="space-y-3 pt-5">
                <label
                  className={cn(
                    "flex cursor-pointer items-start gap-3 rounded-xl border p-3.5 transition-all",
                    notifyOn === "red_yellow"
                      ? "border-primary bg-accent/55 ring-1 ring-primary/25"
                      : "border-border bg-card hover:bg-muted/50"
                  )}
                >
                  <input
                    type="radio"
                    name="notify_on"
                    value="red_yellow"
                    checked={notifyOn === "red_yellow"}
                    onChange={() => setNotifyOn("red_yellow")}
                    disabled={isSaving}
                    className="mt-1 size-4 accent-[var(--brand)]"
                  />
                  <div className="min-w-0 space-y-1">
                    <div className="text-sm font-semibold text-foreground">
                      {t.prod.settings.notifyRedYellowTitle}
                    </div>
                    <p className="text-xs text-muted-foreground leading-relaxed">
                      {t.prod.settings.notifyRedYellowDesc}
                    </p>
                  </div>
                </label>

                <label
                  className={cn(
                    "flex cursor-pointer items-start gap-3 rounded-xl border p-3.5 transition-all",
                    notifyOn === "red"
                      ? "border-primary bg-accent/55 ring-1 ring-primary/25"
                      : "border-border bg-card hover:bg-muted/50"
                  )}
                >
                  <input
                    type="radio"
                    name="notify_on"
                    value="red"
                    checked={notifyOn === "red"}
                    onChange={() => setNotifyOn("red")}
                    disabled={isSaving}
                    className="mt-1 size-4 accent-[var(--brand)]"
                  />
                  <div className="min-w-0 space-y-1">
                    <div className="text-sm font-semibold text-foreground">
                      {t.prod.settings.notifyRedTitle}
                    </div>
                    <p className="text-xs text-muted-foreground leading-relaxed">
                      {t.prod.settings.notifyRedDesc}
                    </p>
                  </div>
                </label>
              </CardContent>
            </Card>

            {/* Approval threshold card */}
            <Card className="min-w-0">
              <CardHeader className="border-b border-border pb-4">
                <CardTitle className="flex items-center gap-2 text-base font-semibold">
                  <ShieldAlert className="size-4 text-muted-foreground" />
                  <span>{t.prod.settings.thresholdCardTitle}</span>
                </CardTitle>
                <CardDescription>
                  {t.prod.settings.thresholdCardDescription}
                </CardDescription>
              </CardHeader>

              <CardContent className="space-y-4 pt-5">
                <div className="flex min-h-11 items-start gap-2.5 rounded-xl border border-border bg-background/70 px-3.5 py-2.5">
                  <Checkbox
                    id="settings-threshold-enabled"
                    checked={thresholdEnabled}
                    onCheckedChange={(checked) => {
                      const next = Boolean(checked);
                      setThresholdEnabled(next);
                      if (!next) {
                        setSaveError(null);
                      }
                    }}
                    disabled={isSaving}
                    className="mt-0.5"
                  />
                  <Label
                    htmlFor="settings-threshold-enabled"
                    className="cursor-pointer text-sm font-medium leading-snug text-foreground"
                  >
                    {t.prod.settings.thresholdEnableLabel}
                  </Label>
                </div>

                {thresholdEnabled ? (
                  <div className="space-y-2">
                    <Label htmlFor="settings-threshold-input">
                      {t.prod.settings.thresholdInputLabel}
                    </Label>
                    <Input
                      id="settings-threshold-input"
                      type="text"
                      inputMode="decimal"
                      value={thresholdInput}
                      onChange={(e) => {
                        setThresholdInput(e.target.value);
                        if (saveError) setSaveError(null);
                      }}
                      placeholder={t.prod.settings.thresholdPlaceholder}
                      disabled={isSaving}
                      className="h-11 rounded-xl font-mono text-base sm:h-10"
                    />
                    {parsedThreshold !== null &&
                      !Number.isNaN(parsedThreshold) && (
                        <p className="text-xs font-medium text-[var(--brand-text)] tabular-nums">
                          {interpolate(t.prod.settings.thresholdPreview, {
                            amount: formatMoney(parsedThreshold),
                          })}
                        </p>
                      )}
                  </div>
                ) : (
                  <p className="rounded-xl border border-dashed border-border bg-muted/35 p-3 text-xs text-muted-foreground leading-relaxed">
                    {t.prod.settings.thresholdDisabledHint}
                  </p>
                )}
              </CardContent>
            </Card>
          </div>

          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <Button
              type="submit"
              size="lg"
              disabled={isSaving}
              className="min-h-11 w-full gap-2 rounded-xl px-6 font-semibold shadow-[0_2px_8px_rgba(0,171,117,0.22)] sm:min-h-10 sm:w-auto"
            >
              {isSaving ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  <span>{t.prod.settings.savingButton}</span>
                </>
              ) : (
                <>
                  <Save className="size-4" />
                  <span>{t.prod.settings.saveButton}</span>
                </>
              )}
            </Button>

            {updatedAt && (
              <span className="text-xs text-muted-foreground">
                {interpolate(t.prod.settings.updatedAtLine, {
                  date: formatDate(updatedAt),
                })}
              </span>
            )}
          </div>
        </form>
      )}
    </div>
  );
}

export default function ProdSettingsPage() {
  return (
    <RequireRole roles={["director"]}>
      <SettingsPageContent />
    </RequireRole>
  );
}
