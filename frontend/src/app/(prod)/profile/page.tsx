"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, Eye, EyeOff, Loader2, ShieldAlert } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
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
  ApiError,
  changePassword,
  extractFieldErrors,
  getProdErrorMessage,
  getProfile,
  updateProfile,
} from "@/lib/prod/api";
import { defaultHomeForRole, useSession } from "@/lib/prod/session";
import type { Session, UserProfile } from "@/lib/prod/types";
import { notify } from "@/lib/toast";
import { cn } from "cn";

type SessionWithPasswordFlag = Session & {
  must_change_password?: boolean;
  user: Session["user"] & { must_change_password?: boolean };
};

function requiresPasswordChange(session: Session | null | undefined): boolean {
  if (!session) return false;
  const extended = session as SessionWithPasswordFlag;
  return Boolean(
    extended.must_change_password || extended.user.must_change_password
  );
}

function getProfileText(
  profileDict: Record<string, unknown>,
  key: string,
  lang: Lang,
  fallback: { en: string; ru: string }
): string {
  const value = profileDict[key];
  if (typeof value === "string" && value.trim()) {
    return value;
  }
  return lang === "ru" ? fallback.ru : fallback.en;
}

export default function ProdProfilePage() {
  const router = useRouter();
  const { t, lang, setLang, interpolate } = useT();
  const { session, refreshSession } = useSession();

  const sessionMustChange = requiresPasswordChange(session);
  const [forcedPasswordChange, setForcedPasswordChange] = useState(false);
  const mustChangePassword = sessionMustChange || forcedPasswordChange;

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
  const currentPasswordInputRef = useRef<HTMLInputElement>(null);

  const profileDict = t.prod.profile as Record<string, unknown>;
  const passwordRequiredTitle = getProfileText(
    profileDict,
    "passwordChangeRequiredTitle",
    lang,
    {
      en: "Password change required",
      ru: "Требуется смена пароля",
    }
  );
  const passwordRequiredDescription = getProfileText(
    profileDict,
    "passwordChangeRequiredDescription",
    lang,
    {
      en: "You signed in with an initial or temporary password. Please set a new password to continue using the system.",
      ru: "Вы вошли с временным или первичным паролем. Установите новый пароль, чтобы продолжить работу в системе.",
    }
  );
  const passwordRequiredSubtitle = getProfileText(
    profileDict,
    "passwordChangeRequiredSubtitle",
    lang,
    {
      en: "Update your password to unlock your workspace.",
      ru: "Обновите пароль, чтобы перейти к работе в системе.",
    }
  );
  const passwordRateLimitedFallback = getProfileText(
    profileDict,
    "passwordChangeRateLimited",
    lang,
    {
      en: "Too many failed password attempts. Please try again in 15 minutes.",
      ru: "Слишком много неудачных попыток смены пароля. Повторите через 15 минут.",
    }
  );

  useEffect(() => {
    if (sessionMustChange) return;
    const controller = new AbortController();
    getProfile(lang, { signal: controller.signal })
      .then((data) => {
        setForcedPasswordChange(false);
        setLoadState({ key: fetchKey, profile: data, error: null });
        setFullName(data.full_name);
        setDefaultLang(data.default_lang);
      })
      .catch((err) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        if (err instanceof ApiError && err.code === "password_change_required") {
          setForcedPasswordChange(true);
          setLoadState({ key: fetchKey, profile: null, error: null });
          return;
        }
        setLoadState((prev) => ({
          key: fetchKey,
          profile: prev?.profile ?? null,
          error: getProdErrorMessage(err),
        }));
      });
    return () => controller.abort();
  }, [fetchKey, lang, sessionMustChange]);

  useEffect(() => {
    if (mustChangePassword) {
      currentPasswordInputRef.current?.focus();
    }
  }, [mustChangePassword]);

  const profile = loadState?.profile ?? null;
  const loadError = loadState?.error ?? null;
  const isLoading =
    !mustChangePassword && (loadState === null || loadState.key !== fetchKey);

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
    const wasForced = mustChangePassword;
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
      setForcedPasswordChange(false);
      await refreshSession();
      const summary = interpolate(t.prod.profile.passwordChangedRevoked, {
        count: res.revoked_sessions,
      });
      notify.success(t.prod.profile.passwordChangedToast, summary);
      if (wasForced) {
        router.replace(defaultHomeForRole(role));
      } else {
        setPasswordSuccess(summary);
      }
    } catch (err) {
      if (
        err instanceof ApiError &&
        (err.status === 429 || err.code === "too_many_attempts")
      ) {
        setPasswordError(err.detail || passwordRateLimitedFallback);
      } else {
        const fieldErrors = extractFieldErrors(err);
        setPasswordError(
          fieldErrors.new_password ||
            fieldErrors.current_password ||
            getProdErrorMessage(err)
        );
      }
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

  const passwordCard = (
    <Card
      className={cn(
        "min-w-0",
        mustChangePassword && "border-foreground/20"
      )}
    >
      <CardHeader className="border-b border-border pb-3.5">
        <CardTitle>{t.prod.profile.passwordCardTitle}</CardTitle>
        <CardDescription>
          {t.prod.profile.passwordCardDescription}
        </CardDescription>
      </CardHeader>

      <CardContent className="pt-4">
        <form onSubmit={handleChangePassword} className="space-y-4">
          {passwordError && (
            <Alert
              variant="destructive"
              className="ui-notice ui-notice-danger"
            >
              <AlertCircle className="size-4" />
              <AlertDescription className="break-words">
                {passwordError}
              </AlertDescription>
            </Alert>
          )}

          {passwordSuccess && (
            <div
              role="status"
              className="ui-notice ui-notice-ok text-sm text-foreground break-words"
            >
              {passwordSuccess}
            </div>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="profile-current-password">
              {t.prod.profile.currentPasswordLabel}
            </Label>
            <div className="relative">
              <Input
                ref={currentPasswordInputRef}
                id="profile-current-password"
                type={showCurrent ? "text" : "password"}
                autoComplete="current-password"
                autoFocus={mustChangePassword}
                value={currentPassword}
                onChange={(e) => {
                  setCurrentPassword(e.target.value);
                  if (passwordError) setPasswordError(null);
                }}
                placeholder={t.prod.profile.currentPasswordPlaceholder}
                disabled={isChangingPassword}
                className="h-10 rounded-[6px] pr-10 sm:h-9"
              />
              <button
                type="button"
                onClick={() => setShowCurrent((v) => !v)}
                aria-label={
                  showCurrent
                    ? t.prod.login.hidePassword
                    : t.prod.login.showPassword
                }
                className="absolute top-1/2 right-1 flex size-8 -translate-y-1/2 items-center justify-center rounded-[4px] text-muted-foreground hover:bg-muted hover:text-foreground sm:size-7"
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
                className="h-10 rounded-[6px] pr-10 sm:h-9"
              />
              <button
                type="button"
                onClick={() => setShowNew((v) => !v)}
                aria-label={
                  showNew
                    ? t.prod.login.hidePassword
                    : t.prod.login.showPassword
                }
                className="absolute top-1/2 right-1 flex size-8 -translate-y-1/2 items-center justify-center rounded-[4px] text-muted-foreground hover:bg-muted hover:text-foreground sm:size-7"
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
                className="h-10 rounded-[6px] pr-10 sm:h-9"
              />
              <button
                type="button"
                onClick={() => setShowConfirm((v) => !v)}
                aria-label={
                  showConfirm
                    ? t.prod.login.hidePassword
                    : t.prod.login.showPassword
                }
                className="absolute top-1/2 right-1 flex size-8 -translate-y-1/2 items-center justify-center rounded-[4px] text-muted-foreground hover:bg-muted hover:text-foreground sm:size-7"
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
            variant={mustChangePassword ? "default" : "outline"}
            disabled={
              isChangingPassword ||
              !currentPassword ||
              !newPassword ||
              !confirmPassword
            }
            className={cn(
              "min-h-11 w-full sm:min-h-9",
              !mustChangePassword && "sm:w-auto"
            )}
          >
            {isChangingPassword ? (
              <>
                <Loader2 className="size-4 animate-spin" />
                <span>{t.prod.profile.changingPassword}</span>
              </>
            ) : (
              <span>{t.prod.profile.changePasswordButton}</span>
            )}
          </Button>
        </form>
      </CardContent>
    </Card>
  );

  if (mustChangePassword) {
    return (
      <div className="mx-auto max-w-lg space-y-4 sm:space-y-5">
        <div className="min-w-0">
          <h1 className="ui-page-title">{passwordRequiredTitle}</h1>
          <p className="ui-page-subtitle">{passwordRequiredSubtitle}</p>
        </div>

        <Alert className="ui-notice ui-notice-warn">
          <ShieldAlert className="size-4 text-[var(--status-warn)]" />
          <AlertTitle>{passwordRequiredTitle}</AlertTitle>
          <AlertDescription className="break-words">
            {passwordRequiredDescription}
          </AlertDescription>
        </Alert>

        {passwordCard}
      </div>
    );
  }

  return (
    <div className="space-y-4 sm:space-y-5">
      <div className="min-w-0">
        <h1 className="ui-page-title">{t.prod.profile.title}</h1>
        <p className="ui-page-subtitle">{t.prod.profile.subtitle}</p>
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
          <Skeleton className="h-80 w-full rounded-[8px]" />
          <Skeleton className="h-80 w-full rounded-[8px]" />
        </div>
      ) : (
        <div className="grid grid-cols-1 items-start gap-4 sm:gap-5 lg:grid-cols-2">
          {/* Personal details & default language */}
          <Card className="min-w-0">
            <CardHeader className="border-b border-border pb-3.5">
              <CardTitle>{t.prod.profile.accountCardTitle}</CardTitle>
              <CardDescription>
                {t.prod.profile.accountCardDescription}
              </CardDescription>
            </CardHeader>

            <CardContent className="space-y-4 pt-4">
              <dl className="ui-dl">
                <div className="ui-dl-row">
                  <dt className="ui-dt">{t.prod.profile.loginLabel}</dt>
                  <dd className="ui-dd font-mono break-all">
                    {profile?.login ?? session?.user.login}
                  </dd>
                </div>
                <div className="ui-dl-row">
                  <dt className="ui-dt">{t.prod.profile.roleLabel}</dt>
                  <dd className="ui-dd">{roleLabel}</dd>
                </div>
                <div className="ui-dl-row">
                  <dt className="ui-dt">{t.prod.profile.companyLabel}</dt>
                  <dd className="ui-dd break-words">{companyLabel}</dd>
                </div>
              </dl>

              <form onSubmit={handleSaveProfile} className="space-y-4">
                {profileError && (
                  <Alert
                    variant="destructive"
                    className="ui-notice ui-notice-danger"
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
                    className="h-10 rounded-[6px] sm:h-9"
                  />
                </div>

                <div className="space-y-1.5">
                  <Label>{t.prod.profile.defaultLangLabel}</Label>
                  <div
                    role="group"
                    aria-label={t.prod.profile.defaultLangLabel}
                    className="inline-flex items-center rounded-[6px] border border-border bg-muted p-0.5"
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
                            "inline-flex min-h-10 min-w-[56px] cursor-pointer items-center justify-center rounded-[4px] border px-3 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50 sm:min-h-8",
                            selected
                              ? "border-border bg-card text-foreground"
                              : "border-transparent text-muted-foreground hover:text-foreground"
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
                  className="min-h-11 w-full sm:min-h-9 sm:w-auto"
                >
                  {isSavingProfile ? (
                    <>
                      <Loader2 className="size-4 animate-spin" />
                      <span>{t.prod.profile.savingProfile}</span>
                    </>
                  ) : (
                    <span>{t.prod.profile.saveProfile}</span>
                  )}
                </Button>
              </form>
            </CardContent>
          </Card>

          {/* Change password card */}
          {passwordCard}
        </div>
      )}
    </div>
  );
}
