"use client";

import { useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, Eye, EyeOff, Loader2 } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
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
import { Separator } from "@/components/ui/separator";
import { LANG_OPTIONS, useT } from "@/i18n";
import {
  ApiError,
  getProdErrorMessage,
  getProfile,
  login as apiLogin,
} from "@/lib/prod/api";
import { defaultHomeForRole, useSession } from "@/lib/prod/session";
import type { Session } from "@/lib/prod/types";
import { cn } from "cn";

type SessionWithPasswordFlag = Session & {
  must_change_password?: boolean;
  user: Session["user"] & { must_change_password?: boolean };
};

function requiresPasswordChange(session: Session): boolean {
  const extended = session as SessionWithPasswordFlag;
  return Boolean(
    extended.must_change_password || extended.user.must_change_password
  );
}

const SHOW_DEMO_LOGINS = process.env.NEXT_PUBLIC_DEMO_LOGINS === "1";

const DEMO_LOGIN_PRESETS = [
  { login: "accountant", labelKey: "demoLoginAccountant" },
  { login: "director", labelKey: "demoLoginDirector" },
  { login: "analyst", labelKey: "demoLoginAnalyst" },
] as const;

export default function ProdLoginPage() {
  const router = useRouter();
  const { t, lang, setLang } = useT();
  const { setSession } = useSession();

  const [loginValue, setLoginValue] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const passwordInputRef = useRef<HTMLInputElement>(null);

  const handleSelectDemoLogin = (presetLogin: string) => {
    setLoginValue(presetLogin);
    if (error) setError(null);
    passwordInputRef.current?.focus();
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    const trimmedLogin = loginValue.trim();
    if (!trimmedLogin || !password) {
      setError(t.prod.login.errorFillBoth);
      return;
    }

    setIsSubmitting(true);
    try {
      const session = await apiLogin(
        { login: trimmedLogin, password },
        lang
      );
      let mustChange = requiresPasswordChange(session);
      if (!mustChange) {
        try {
          const profile = await getProfile(lang, {
            suppressAuthRedirect: true,
          });
          if (profile.default_lang && profile.default_lang !== lang) {
            setLang(profile.default_lang);
          }
        } catch (profileErr) {
          if (
            profileErr instanceof ApiError &&
            profileErr.code === "password_change_required"
          ) {
            mustChange = true;
          }
          // Non-blocking language preference sync.
        }
      }
      setSession(session);
      router.replace(
        mustChange ? "/profile" : defaultHomeForRole(session.user.role)
      );
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.code === "invalid_credentials") {
          setError(err.detail || t.prod.login.errorInvalidCredentials);
        } else if (err.code === "too_many_attempts" || err.status === 429) {
          setError(err.detail || t.prod.login.errorTooManyAttempts);
        } else {
          setError(getProdErrorMessage(err));
        }
      } else {
        setError(getProdErrorMessage(err));
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col bg-background">
      <header className="border-b border-border bg-card">
        <div className="mx-auto flex w-full max-w-[1248px] items-center justify-between gap-3 px-4 py-2.5 sm:px-6">
          <div className="flex min-w-0 items-center gap-2">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/logo.svg"
              alt=""
              width={28}
              height={28}
              className="h-7 w-7 shrink-0"
            />
            <span className="truncate text-[15px] font-semibold tracking-tight text-foreground">
              {t.brand.name}
            </span>
          </div>

          <div
            className="inline-flex items-center rounded-[6px] border border-border bg-muted p-0.5"
            role="group"
            aria-label={t.nav.langAriaLabel}
          >
            {LANG_OPTIONS.map((option) => {
              const isSelected = lang === option.code;
              return (
                <button
                  key={option.code}
                  type="button"
                  aria-pressed={isSelected}
                  onClick={() => setLang(option.code)}
                  className={cn(
                    "inline-flex min-h-9 w-[40px] cursor-pointer items-center justify-center rounded-[4px] border text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:min-h-7",
                    isSelected
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
      </header>

      <main className="flex flex-1 items-center justify-center px-4 py-10 sm:px-6">
        <Card className="w-full max-w-sm rounded-[8px] shadow-none">
          <CardHeader className="space-y-1">
            <CardTitle className="text-lg font-semibold tracking-tight">
              {t.prod.login.title}
            </CardTitle>
            <CardDescription>{t.prod.login.subtitle}</CardDescription>
          </CardHeader>

          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              {error && (
                <Alert variant="destructive">
                  <AlertCircle className="size-4" />
                  <AlertDescription className="break-words">
                    {error}
                  </AlertDescription>
                </Alert>
              )}

              <div className="space-y-1.5">
                <Label htmlFor="prod-login-input">
                  {t.prod.login.loginLabel}
                </Label>
                <Input
                  id="prod-login-input"
                  name="login"
                  type="text"
                  autoComplete="username"
                  autoFocus
                  placeholder={t.prod.login.loginPlaceholder}
                  value={loginValue}
                  onChange={(e) => {
                    setLoginValue(e.target.value);
                    if (error) setError(null);
                  }}
                  disabled={isSubmitting}
                  className="h-10 rounded-[6px] sm:h-9"
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="prod-password-input">
                  {t.prod.login.passwordLabel}
                </Label>
                <div className="relative">
                  <Input
                    ref={passwordInputRef}
                    id="prod-password-input"
                    name="password"
                    type={showPassword ? "text" : "password"}
                    autoComplete="current-password"
                    placeholder={t.prod.login.passwordPlaceholder}
                    value={password}
                    onChange={(e) => {
                      setPassword(e.target.value);
                      if (error) setError(null);
                    }}
                    disabled={isSubmitting}
                    className="h-10 rounded-[6px] pr-10 sm:h-9"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((prev) => !prev)}
                    aria-label={
                      showPassword
                        ? t.prod.login.hidePassword
                        : t.prod.login.showPassword
                    }
                    className="absolute top-1/2 right-1 flex size-8 -translate-y-1/2 cursor-pointer items-center justify-center rounded-[4px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    {showPassword ? (
                      <EyeOff className="size-4" />
                    ) : (
                      <Eye className="size-4" />
                    )}
                  </button>
                </div>
              </div>

              <Button
                type="submit"
                disabled={isSubmitting}
                className="min-h-11 w-full sm:min-h-9"
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="size-4 animate-spin" />
                    <span>{t.prod.login.submitting}</span>
                  </>
                ) : (
                  <span>{t.prod.login.submit}</span>
                )}
              </Button>
            </form>

            {SHOW_DEMO_LOGINS && (
              <div className="mt-4 space-y-2.5">
                <Separator />
                <div className="space-y-0.5 pt-1">
                  <div className="ui-label-meta">
                    {t.prod.login.demoLoginsTitle}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {t.prod.login.demoLoginsHint}
                  </p>
                </div>
                <div className="flex flex-col gap-2">
                  {DEMO_LOGIN_PRESETS.map((preset) => (
                    <Button
                      key={preset.login}
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={isSubmitting}
                      onClick={() => handleSelectDemoLogin(preset.login)}
                      className="min-h-10 w-full justify-between font-normal sm:min-h-8"
                    >
                      <span>{t.prod.login[preset.labelKey]}</span>
                      <span className="font-mono text-xs text-muted-foreground">
                        {preset.login}
                      </span>
                    </Button>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
