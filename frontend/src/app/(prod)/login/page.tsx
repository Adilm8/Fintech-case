"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  BadgeCheck,
  Eye,
  EyeOff,
  Loader2,
  LogIn,
} from "lucide-react";
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
import { LANG_OPTIONS, useT } from "@/i18n";
import { ApiError, getProdErrorMessage, login as apiLogin } from "@/lib/prod/api";
import { defaultHomeForRole, useSession } from "@/lib/prod/session";
import { cn } from "cn";

export default function ProdLoginPage() {
  const router = useRouter();
  const { t, lang, setLang } = useT();
  const { setSession } = useSession();

  const [loginValue, setLoginValue] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      setSession(session);
      router.replace(defaultHomeForRole(session.user.role));
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
      <header className="border-b border-border bg-card/90">
        <div className="mx-auto flex w-full max-w-[1248px] items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <div className="flex min-w-0 items-center gap-2.5">
            <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-[0_2px_8px_rgba(0,171,117,0.28)]">
              <BadgeCheck className="size-5" />
            </div>
            <div className="min-w-0">
              <div className="text-sm font-semibold leading-tight tracking-tight text-foreground sm:text-base">
                {t.brand.name}
              </div>
              <div className="hidden text-xs leading-snug text-muted-foreground sm:block">
                {t.brand.subtitle}
              </div>
            </div>
          </div>

          <div
            className="inline-flex items-center rounded-xl border border-border bg-background p-0.5"
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
                    "inline-flex min-h-9 w-[42px] cursor-pointer items-center justify-center rounded-[10px] text-xs font-semibold tracking-wide transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:min-h-8",
                    isSelected
                      ? "bg-card text-[var(--brand-text)] shadow-xs ring-1 ring-border/70"
                      : "text-muted-foreground hover:text-foreground"
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
        <Card className="w-full max-w-md shadow-sm">
          <CardHeader className="space-y-1.5 pb-4">
            <CardTitle className="text-xl font-semibold tracking-tight">
              {t.prod.login.title}
            </CardTitle>
            <CardDescription>{t.prod.login.subtitle}</CardDescription>
          </CardHeader>

          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              {error && (
                <Alert
                  variant="destructive"
                  className="border-red-300 bg-red-50/90"
                >
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
                  className="h-11 rounded-xl sm:h-10"
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="prod-password-input">
                  {t.prod.login.passwordLabel}
                </Label>
                <div className="relative">
                  <Input
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
                    className="h-11 rounded-xl pr-11 sm:h-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((prev) => !prev)}
                    aria-label={
                      showPassword
                        ? t.prod.login.hidePassword
                        : t.prod.login.showPassword
                    }
                    className="absolute top-1/2 right-1.5 flex size-8 -translate-y-1/2 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
                size="lg"
                disabled={isSubmitting}
                className="min-h-11 w-full gap-2 rounded-xl font-semibold shadow-[0_2px_8px_rgba(0,171,117,0.22)]"
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="size-4 animate-spin" />
                    <span>{t.prod.login.submitting}</span>
                  </>
                ) : (
                  <>
                    <LogIn className="size-4" />
                    <span>{t.prod.login.submit}</span>
                  </>
                )}
              </Button>
            </form>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
