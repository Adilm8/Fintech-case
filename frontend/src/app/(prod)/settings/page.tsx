"use client";

import { useEffect, useState, type FormEvent } from "react";
import { AlertCircle, Loader2 } from "lucide-react";
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
    <div className="space-y-4 sm:space-y-5">
      <div className="min-w-0">
        <h1 className="ui-page-title">{t.prod.settings.title}</h1>
        <p className="ui-page-subtitle">{t.prod.settings.subtitle}</p>
      </div>

      {loadError && (
        <Alert variant="destructive" className="ui-notice ui-notice-danger">
          <AlertCircle className="size-4" />
          <AlertTitle>{t.common.serverErrorTitle}</AlertTitle>
          <AlertDescription className="break-words">{loadError}</AlertDescription>
        </Alert>
      )}

      {isLoading ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Skeleton className="h-56 w-full rounded-[8px]" />
          <Skeleton className="h-56 w-full rounded-[8px]" />
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4 sm:space-y-5">
          {saveError && (
            <Alert variant="destructive" className="ui-notice ui-notice-danger">
              <AlertCircle className="size-4" />
              <AlertDescription className="break-words">
                {saveError}
              </AlertDescription>
            </Alert>
          )}

          <div className="grid grid-cols-1 items-start gap-4 sm:gap-5 lg:grid-cols-2">
            {/* Notification mode card */}
            <Card className="min-w-0">
              <CardHeader className="border-b border-border pb-3.5">
                <CardTitle>{t.prod.settings.notifyCardTitle}</CardTitle>
                <CardDescription>
                  {t.prod.settings.notifyCardDescription}
                </CardDescription>
              </CardHeader>

              <CardContent className="space-y-2.5 pt-4">
                <label
                  className={cn(
                    "flex cursor-pointer items-start gap-3 rounded-[6px] border p-3.5 transition-colors",
                    notifyOn === "red_yellow"
                      ? "border-foreground bg-muted/40"
                      : "border-border bg-card hover:bg-muted/30"
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
                  <div className="min-w-0 space-y-0.5">
                    <div className="text-sm font-medium text-foreground">
                      {t.prod.settings.notifyRedYellowTitle}
                    </div>
                    <p className="text-xs text-muted-foreground leading-relaxed">
                      {t.prod.settings.notifyRedYellowDesc}
                    </p>
                  </div>
                </label>

                <label
                  className={cn(
                    "flex cursor-pointer items-start gap-3 rounded-[6px] border p-3.5 transition-colors",
                    notifyOn === "red"
                      ? "border-foreground bg-muted/40"
                      : "border-border bg-card hover:bg-muted/30"
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
                  <div className="min-w-0 space-y-0.5">
                    <div className="text-sm font-medium text-foreground">
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
              <CardHeader className="border-b border-border pb-3.5">
                <CardTitle>{t.prod.settings.thresholdCardTitle}</CardTitle>
                <CardDescription>
                  {t.prod.settings.thresholdCardDescription}
                </CardDescription>
              </CardHeader>

              <CardContent className="space-y-4 pt-4">
                <div className="ui-subpanel flex min-h-11 items-start gap-2.5">
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
                  <div className="space-y-1.5">
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
                      className="h-10 rounded-[6px] bg-card font-mono tabular-nums sm:h-9"
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
                  <p className="ui-subpanel text-xs text-muted-foreground leading-relaxed">
                    {t.prod.settings.thresholdDisabledHint}
                  </p>
                )}
              </CardContent>
            </Card>
          </div>

          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <Button
              type="submit"
              disabled={isSaving}
              className="min-h-11 w-full sm:min-h-9 sm:w-auto"
            >
              {isSaving ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  <span>{t.prod.settings.savingButton}</span>
                </>
              ) : (
                <span>{t.prod.settings.saveButton}</span>
              )}
            </Button>

            {updatedAt && (
              <span className="text-xs text-muted-foreground tabular-nums">
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
