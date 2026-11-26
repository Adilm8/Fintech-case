"use client";

import { useEffect, useState, type FormEvent } from "react";
import {
  AlertCircle,
  Building2,
  CheckCircle2,
  Eye,
  EyeOff,
  KeyRound,
  Landmark,
  Loader2,
  Save,
  UserCircle2,
} from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { LANG_OPTIONS, useT, type Lang } from "@/i18n";
import {
  changePassword,
  extractFieldErrors,
  getProdErrorMessage,
  getProfile,
  updateProfile,
} from "@/lib/prod/api";
import { useSession } from "@/lib/prod/session";
import type { UserProfile } from "@/lib/prod/types";
import { notify } from "@/lib/toast";
import { cn } from "cn";

export default function ProdProfilePage() {
  const { t, lang, setLang, interpolate } = useT();
  const { session, refreshSession } = useSession();

  const fetchKey = lang;
  const [loadState, setLoadState] = useState<{
    key: string;
    profile: UserProfile | null;
    error: string | null;
  } | null>(null);

  // Personal details form state
  const [fullName, setFullName] = useState("");
  const [defaultLang, setDefaultLang] = useState<Lang>("ru");
  const [isSavingProfile, setIsSavingProfile] = useState(false);
  const [profileError, setProfileError] = useState<string | null>(null);

  // Change password form state
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [isChangingPassword, setIsChangingPassword] = useState(false);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordSuccess, setPasswordSuccess] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getProfile(lang, { signal: controller.signal })
      .then((data) => {
        setLoadState({ key: fetchKey, profile: data, error: null });
        setFullName(data.full_name);
        setDefaultLang(data.default_lang);
      })
      .catch((err) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setLoadState((prev) => ({
          key: fetchKey,
          profile: prev?.profile ?? null,
          error: getProdErrorMessage(err),
        }));
      });
    return () => controller.abort();
  }, [fetchKey, lang]);

  const profile = loadState?.profile ?? null;
  const loadError = loadState?.error ?? null;
  const isLoading = loadState === null || loadState.key !== fetchKey;

  const handleSaveProfile = async (e: FormEvent) => {
    e.preventDefault();
    setProfileError(null);

    const trimmedName = fullName.trim();
    if (!trimmedName) {
      setProfileError(t.prod.profile.fullNameRequired);
      return;
    }

    setIsSavingProfile(true);
    try {
      const updated = await updateProfile(
        { full_name: trimmedName, default_lang: defaultLang },
        lang
      );
      setLoadState({ key: updated.default_lang, profile: updated, error: null });
      setFullName(updated.full_name);
      setDefaultLang(updated.default_lang);
      setLang(updated.default_lang);
      await refreshSession();
      notify.success(t.prod.profile.profileSavedToast);
    } catch (err) {
      const fieldErrors = extractFieldErrors(err);
      setProfileError(fieldErrors.full_name || getProdErrorMessage(err));
    } finally {
      setIsSavingProfile(false);
    }
  };

  const handleChangePassword = async (e: FormEvent) => {
    e.preventDefault();
    setPasswordError(null);
    setPasswordSuccess(null);

    if (newPassword.length < 8) {
      setPasswordError(t.prod.profile.passwordTooShort);
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordError(t.prod.profile.passwordMismatch);
      return;
    }

    setIsChangingPassword(true);
    try {
      const res = await changePassword(
        {
          current_password: currentPassword,
          new_password: newPassword,
        },
        lang
      );
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      const summary = interpolate(t.prod.profile.passwordChangedRevoked, {
        count: res.revoked_sessions,
      });
      setPasswordSuccess(summary);
      notify.success(t.prod.profile.passwordChangedToast, summary);
    } catch (err) {
      const fieldErrors = extractFieldErrors(err);
      setPasswordError(
        fieldErrors.new_password ||
          fieldErrors.current_password ||
          getProdErrorMessage(err)
      );
    } finally {
      setIsChangingPassword(false);
    }
  };

  const role = profile?.role ?? session?.user.role ?? "accountant";
  const roleLabel = t.prod.roles[role];
  const companyLabel =
    profile?.company?.name ??
    session?.company?.name ??
    t.prod.roles.bankAnalystCompany;

  return (
    <div className="space-y-5 sm:space-y-6">
      <div className="min-w-0">
        <div className="flex items-center gap-2.5">
          <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-accent text-[var(--brand-text)]">
            <UserCircle2 className="size-5" />
          </div>
          <h1 className="text-xl font-semibold tracking-tight text-foreground sm:text-2xl">
            {t.prod.profile.title}
          </h1>
        </div>
        <p className="mt-1.5 text-sm text-muted-foreground">
          {t.prod.profile.subtitle}
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
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
          <Skeleton className="h-80 w-full rounded-2xl" />
          <Skeleton className="h-80 w-full rounded-2xl" />
        </div>
      ) : (
        <div className="grid grid-cols-1 items-start gap-5 lg:grid-cols-2">
          {/* Personal details & default language */}
          <Card className="min-w-0">
            <CardHeader className="border-b border-border pb-4">
              <CardTitle className="text-base font-semibold">
                {t.prod.profile.accountCardTitle}
              </CardTitle>
              <CardDescription>
                {t.prod.profile.accountCardDescription}
              </CardDescription>
            </CardHeader>

            <CardContent className="pt-5">
              <div className="mb-5 grid grid-cols-1 gap-2.5 rounded-xl border border-border bg-background/70 p-3.5 text-xs sm:grid-cols-2">
                <div className="space-y-0.5 min-w-0">
                  <div className="text-muted-foreground">
                    {t.prod.profile.loginLabel}
                  </div>
                  <div className="font-mono text-sm font-semibold text-foreground break-all">
                    {profile?.login ?? session?.user.login}
                  </div>
                </div>

                <div className="space-y-1 min-w-0">
                  <div className="text-muted-foreground">
                    {t.prod.profile.roleLabel}
                  </div>
                  <Badge variant="secondary" className="h-auto px-2 py-0.5 text-xs">
                    {roleLabel}
                  </Badge>
                </div>

                <div className="space-y-0.5 sm:col-span-2 min-w-0">
                  <div className="text-muted-foreground">
                    {t.prod.profile.companyLabel}
                  </div>
                  <div className="flex items-center gap-1.5 text-sm font-medium text-foreground break-words">
                    {profile?.company ? (
                      <Building2 className="size-3.5 shrink-0 text-muted-foreground" />
                    ) : (
                      <Landmark className="size-3.5 shrink-0 text-[var(--brand-text)]" />
                    )}
                    <span>{companyLabel}</span>
                  </div>
                </div>
              </div>

              <form onSubmit={handleSaveProfile} className="space-y-4">
                {profileError && (
                  <Alert
                    variant="destructive"
                    className="rounded-xl border-red-300 bg-red-50/90"
                  >
                    <AlertCircle className="size-4" />
                    <AlertDescription className="break-words">
                      {profileError}
                    </AlertDescription>
                  </Alert>
                )}

                <div className="space-y-1.5">
                  <Label htmlFor="profile-full-name">
                    {t.prod.profile.fullNameLabel}
                  </Label>
                  <Input
                    id="profile-full-name"
                    type="text"
                    maxLength={120}
                    value={fullName}
                    onChange={(e) => {
                      setFullName(e.target.value);
                      if (profileError) setProfileError(null);
                    }}
                    placeholder={t.prod.profile.fullNamePlaceholder}
                    disabled={isSavingProfile}
                    className="h-11 rounded-xl sm:h-10"
                  />
                </div>

                <div className="space-y-1.5">
                  <Label>{t.prod.profile.defaultLangLabel}</Label>
                  <div
                    role="group"
                    aria-label={t.prod.profile.defaultLangLabel}
                    className="inline-flex items-center rounded-xl border border-border bg-background p-1"
                  >
                    {LANG_OPTIONS.map((option) => {
                      const selected = defaultLang === option.code;
                      return (
                        <button
                          key={option.code}
                          type="button"
                          aria-pressed={selected}
                          onClick={() => setDefaultLang(option.code)}
                          disabled={isSavingProfile}
                          className={cn(
                            "inline-flex min-h-10 min-w-[64px] cursor-pointer items-center justify-center rounded-lg px-3 text-xs font-semibold tracking-wide transition-all sm:min-h-8",
                            selected
                              ? "bg-card text-[var(--brand-text)] shadow-xs ring-1 ring-border"
                              : "text-muted-foreground hover:text-foreground"
                          )}
                        >
                          {option.label}
                        </button>
                      );
                    })}
                  </div>
                </div>

                <Button
                  type="submit"
                  disabled={isSavingProfile}
                  className="min-h-11 w-full gap-2 rounded-xl font-semibold sm:min-h-10 sm:w-auto"
                >
                  {isSavingProfile ? (
                    <>
                      <Loader2 className="size-4 animate-spin" />
                      <span>{t.prod.profile.savingProfile}</span>
                    </>
                  ) : (
                    <>
                      <Save className="size-4" />
                      <span>{t.prod.profile.saveProfile}</span>
                    </>
                  )}
                </Button>
              </form>
            </CardContent>
          </Card>

          {/* Change password card */}
          <Card className="min-w-0">
            <CardHeader className="border-b border-border pb-4">
              <CardTitle className="flex items-center gap-2 text-base font-semibold">
                <KeyRound className="size-4 text-muted-foreground" />
                <span>{t.prod.profile.passwordCardTitle}</span>
              </CardTitle>
              <CardDescription>
                {t.prod.profile.passwordCardDescription}
              </CardDescription>
            </CardHeader>

            <CardContent className="pt-5">
              <form onSubmit={handleChangePassword} className="space-y-4">
                {passwordError && (
                  <Alert
                    variant="destructive"
                    className="rounded-xl border-red-300 bg-red-50/90"
                  >
                    <AlertCircle className="size-4" />
                    <AlertDescription className="break-words">
                      {passwordError}
                    </AlertDescription>
                  </Alert>
                )}

                {passwordSuccess && (
                  <Alert className="rounded-xl border-[#00AB75]/35 bg-[#E8F8F2] text-[#064A34]">
                    <CheckCircle2 className="size-4 text-[var(--brand-text)]" />
                    <AlertDescription className="break-words text-[#064A34]">
                      {passwordSuccess}
                    </AlertDescription>
                  </Alert>
                )}

                <div className="space-y-1.5">
                  <Label htmlFor="profile-current-password">
                    {t.prod.profile.currentPasswordLabel}
                  </Label>
                  <div className="relative">
                    <Input
                      id="profile-current-password"
                      type={showCurrent ? "text" : "password"}
                      autoComplete="current-password"
                      value={currentPassword}
                      onChange={(e) => {
                        setCurrentPassword(e.target.value);
                        if (passwordError) setPasswordError(null);
                      }}
                      placeholder={t.prod.profile.currentPasswordPlaceholder}
                      disabled={isChangingPassword}
                      className="h-11 rounded-xl pr-11 sm:h-10"
                    />
                    <button
                      type="button"
                      onClick={() => setShowCurrent((v) => !v)}
                      aria-label={
                        showCurrent
                          ? t.prod.login.hidePassword
                          : t.prod.login.showPassword
                      }
                      className="absolute top-1/2 right-1.5 flex size-8 -translate-y-1/2 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground"
                    >
                      {showCurrent ? (
                        <EyeOff className="size-4" />
                      ) : (
                        <Eye className="size-4" />
                      )}
                    </button>
                  </div>
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="profile-new-password">
                    {t.prod.profile.newPasswordLabel}
                  </Label>
                  <div className="relative">
                    <Input
                      id="profile-new-password"
                      type={showNew ? "text" : "password"}
                      autoComplete="new-password"
                      value={newPassword}
                      onChange={(e) => {
                        setNewPassword(e.target.value);
                        if (passwordError) setPasswordError(null);
                      }}
                      placeholder={t.prod.profile.newPasswordPlaceholder}
                      disabled={isChangingPassword}
                      className="h-11 rounded-xl pr-11 sm:h-10"
                    />
                    <button
                      type="button"
                      onClick={() => setShowNew((v) => !v)}
                      aria-label={
                        showNew
                          ? t.prod.login.hidePassword
                          : t.prod.login.showPassword
                      }
                      className="absolute top-1/2 right-1.5 flex size-8 -translate-y-1/2 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground"
                    >
                      {showNew ? (
                        <EyeOff className="size-4" />
                      ) : (
                        <Eye className="size-4" />
                      )}
                    </button>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {t.prod.profile.passwordHint}
                  </p>
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="profile-confirm-password">
                    {t.prod.profile.confirmPasswordLabel}
                  </Label>
                  <div className="relative">
                    <Input
                      id="profile-confirm-password"
                      type={showConfirm ? "text" : "password"}
                      autoComplete="new-password"
                      value={confirmPassword}
                      onChange={(e) => {
                        setConfirmPassword(e.target.value);
                        if (passwordError) setPasswordError(null);
                      }}
                      placeholder={t.prod.profile.confirmPasswordPlaceholder}
                      disabled={isChangingPassword}
                      className="h-11 rounded-xl pr-11 sm:h-10"
                    />
                    <button
                      type="button"
                      onClick={() => setShowConfirm((v) => !v)}
                      aria-label={
                        showConfirm
                          ? t.prod.login.hidePassword
                          : t.prod.login.showPassword
                      }
                      className="absolute top-1/2 right-1.5 flex size-8 -translate-y-1/2 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground"
                    >
                      {showConfirm ? (
                        <EyeOff className="size-4" />
                      ) : (
                        <Eye className="size-4" />
                      )}
                    </button>
                  </div>
                </div>

                <Button
                  type="submit"
                  variant="outline"
                  disabled={
                    isChangingPassword ||
                    !currentPassword ||
                    !newPassword ||
                    !confirmPassword
                  }
                  className="min-h-11 w-full gap-2 rounded-xl font-semibold sm:min-h-10 sm:w-auto"
                >
                  {isChangingPassword ? (
                    <>
                      <Loader2 className="size-4 animate-spin" />
                      <span>{t.prod.profile.changingPassword}</span>
                    </>
                  ) : (
                    <>
                      <KeyRound className="size-4" />
                      <span>{t.prod.profile.changePasswordButton}</span>
                    </>
                  )}
                </Button>
              </form>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
