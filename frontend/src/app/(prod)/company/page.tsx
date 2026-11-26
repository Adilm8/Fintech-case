"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
} from "react";
import {
  AlertCircle,
  AlertTriangle,
  Check,
  Copy,
  Loader2,
  RefreshCw,
} from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useT } from "@/i18n";
import {
  extractFieldErrors,
  getCompany,
  getProdErrorMessage,
  inviteCompanyUser,
  updateCompanyUser,
} from "@/lib/prod/api";
import { RequireRole, useSession } from "@/lib/prod/session";
import type {
  CompanyDetail,
  CompanyRole,
  CompanyUser,
  InviteUserResponse,
} from "@/lib/prod/types";
import { notify } from "@/lib/toast";
import { cn } from "cn";

function CompanyPageContent() {
  const { t, lang, formatDate, interpolate } = useT();
  const { session, refreshSession } = useSession();

  const [refreshNonce, setRefreshNonce] = useState(0);
  const fetchKey = `${lang}|${refreshNonce}`;
  const [loadState, setLoadState] = useState<{
    key: string;
    company: CompanyDetail | null;
    error: string | null;
  } | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [updatingUserId, setUpdatingUserId] = useState<number | null>(null);

  // Invite dialog state
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteLogin, setInviteLogin] = useState("");
  const [inviteFullName, setInviteFullName] = useState("");
  const [inviteRole, setInviteRole] = useState<CompanyRole>("accountant");
  const [isInviting, setIsInviting] = useState(false);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [inviteResult, setInviteResult] = useState<InviteUserResponse | null>(
    null
  );
  const [copiedPassword, setCopiedPassword] = useState(false);

  const isDirector = session?.user.role === "director";

  useEffect(() => {
    const controller = new AbortController();
    getCompany(lang, { signal: controller.signal })
      .then((data) => {
        setLoadState({ key: fetchKey, company: data, error: null });
      })
      .catch((err) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setLoadState((prev) => ({
          key: fetchKey,
          company: prev?.company ?? null,
          error: getProdErrorMessage(err),
        }));
      });
    return () => controller.abort();
  }, [fetchKey, lang]);

  const company = loadState?.company ?? null;
  const error = loadState?.error ?? null;
  const isLoading = loadState === null || loadState.key !== fetchKey;

  const handleRefresh = useCallback(() => {
    setRefreshNonce((n) => n + 1);
  }, []);

  const activeDirectorsCount = useMemo(() => {
    if (!company) return 0;
    return company.users.filter((u) => u.role === "director" && u.is_active)
      .length;
  }, [company]);

  const isLastActiveDirector = (u: CompanyUser) =>
    u.role === "director" && u.is_active && activeDirectorsCount <= 1;

  const handleUpdateUser = async (
    target: CompanyUser,
    patch: { role?: CompanyRole; is_active?: boolean }
  ) => {
    if (!isDirector || updatingUserId !== null) return;
    setActionError(null);
    setUpdatingUserId(target.id);
    try {
      const updated = await updateCompanyUser(target.id, patch, lang);
      setLoadState((prev) =>
        prev && prev.company
          ? {
              ...prev,
              company: {
                ...prev.company,
                users: prev.company.users.map((u) =>
                  u.id === updated.id ? updated : u
                ),
              },
            }
          : prev
      );
      if (target.id === session?.user.id) {
        await refreshSession();
      }
      notify.success(t.prod.company.userUpdatedToast);
    } catch (err) {
      const msg = getProdErrorMessage(err);
      setActionError(msg);
      notify.error(t.check.actionErrorTitle, msg);
    } finally {
      setUpdatingUserId(null);
    }
  };

  const openInviteDialog = () => {
    setInviteLogin("");
    setInviteFullName("");
    setInviteRole("accountant");
    setInviteError(null);
    setInviteResult(null);
    setCopiedPassword(false);
    setInviteOpen(true);
  };

  const closeInviteDialog = (nextOpen: boolean) => {
    if (!nextOpen && isInviting) return;
    if (!nextOpen) {
      setInviteOpen(false);
      setInviteResult(null);
      setInviteError(null);
      setCopiedPassword(false);
    }
  };

  const handleInviteSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!isDirector || isInviting) return;
    setInviteError(null);
    setIsInviting(true);
    try {
      const res = await inviteCompanyUser(
        {
          login: inviteLogin.trim(),
          full_name: inviteFullName.trim(),
          role: inviteRole,
        },
        lang
      );
      setInviteResult(res);
      setLoadState((prev) =>
        prev && prev.company
          ? {
              ...prev,
              company: {
                ...prev.company,
                users: [...prev.company.users, res.user],
              },
            }
          : prev
      );
      notify.success(
        interpolate(t.prod.company.inviteDialog.createdToast, {
          login: res.user.login,
        })
      );
    } catch (err) {
      const fieldErrors = extractFieldErrors(err);
      setInviteError(
        fieldErrors.login ||
          fieldErrors.full_name ||
          fieldErrors.role ||
          getProdErrorMessage(err)
      );
    } finally {
      setIsInviting(false);
    }
  };

  const handleCopyTempPassword = async () => {
    if (!inviteResult) return;
    try {
      await navigator.clipboard.writeText(inviteResult.temporary_password);
      setCopiedPassword(true);
      window.setTimeout(() => setCopiedPassword(false), 2500);
    } catch {
      // Fallback: let user copy manually from the read-only input.
    }
  };

  return (
    <div className="space-y-4 sm:space-y-5">
      <div className="ui-page-header">
        <div className="min-w-0">
          <h1 className="ui-page-title">{t.prod.company.title}</h1>
          <p className="ui-page-subtitle">{t.prod.company.subtitle}</p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {isDirector && (
            <Button
              type="button"
              onClick={openInviteDialog}
              className="min-h-10 sm:min-h-9"
            >
              {t.prod.company.inviteButton}
            </Button>
          )}

          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleRefresh}
            disabled={isLoading}
            className="min-h-10 gap-1.5 sm:min-h-9"
          >
            <RefreshCw className={cn("size-3.5", isLoading && "animate-spin")} />
            <span>{t.common.refresh}</span>
          </Button>
        </div>
      </div>

      {error && (
        <Alert variant="destructive" className="ui-notice ui-notice-danger">
          <AlertTriangle className="size-4" />
          <AlertTitle>{t.common.serverErrorTitle}</AlertTitle>
          <AlertDescription className="break-words">{error}</AlertDescription>
        </Alert>
      )}

      {actionError && (
        <Alert variant="destructive" className="ui-notice ui-notice-danger">
          <AlertCircle className="size-4" />
          <AlertTitle>{t.check.actionErrorTitle}</AlertTitle>
          <AlertDescription className="break-words">
            {actionError}
          </AlertDescription>
        </Alert>
      )}

      {isLoading && !company ? (
        <div className="space-y-4">
          <Skeleton className="h-44 w-full rounded-[8px]" />
          <Skeleton className="h-64 w-full rounded-[8px]" />
        </div>
      ) : (
        company && (
          <>
            {/* Company requisites summary card */}
            <Card className="min-w-0">
              <CardHeader className="pb-2">
                <CardTitle>{company.name}</CardTitle>
                <CardDescription>{t.prod.company.detailsTitle}</CardDescription>
              </CardHeader>
              <CardContent>
                <dl className="ui-dl">
                  <div className="ui-dl-row">
                    <dt className="ui-dt">{t.prod.company.binLabel}</dt>
                    <dd className="ui-dd font-mono tabular-nums">
                      {company.bin}
                    </dd>
                  </div>
                  <div className="ui-dl-row">
                    <dt className="ui-dt">{t.prod.company.iikLabel}</dt>
                    <dd className="ui-dd font-mono tabular-nums break-all">
                      {company.iik}
                    </dd>
                  </div>
                  <div className="ui-dl-row">
                    <dt className="ui-dt">{t.prod.company.bikLabel}</dt>
                    <dd className="ui-dd font-mono">{company.bik}</dd>
                  </div>
                  <div className="ui-dl-row">
                    <dt className="ui-dt">{t.prod.company.usersCountLabel}</dt>
                    <dd className="ui-dd font-medium tabular-nums">
                      {company.users.length}
                    </dd>
                  </div>
                  <div className="ui-dl-row">
                    <dt className="ui-dt">
                      {t.prod.company.directorsCountLabel}
                    </dt>
                    <dd className="ui-dd font-medium tabular-nums">
                      {activeDirectorsCount}
                    </dd>
                  </div>
                </dl>
              </CardContent>
            </Card>

            {/* Company users card */}
            <Card className="min-w-0 py-0">
              <CardHeader className="border-b border-border p-4">
                <CardTitle>{t.prod.company.usersTitle}</CardTitle>
                <CardDescription>
                  {isDirector
                    ? t.prod.company.usersSubtitleDirector
                    : t.prod.company.usersSubtitleReadOnly}
                </CardDescription>
              </CardHeader>

              <CardContent className="p-0">
                {/* Mobile flat list (< md) */}
                <div className="divide-y divide-border md:hidden">
                  {company.users.map((u) => {
                    const isSelf = u.id === session?.user.id;
                    const protectedLastDir = isLastActiveDirector(u);
                    const isBusy = updatingUserId === u.id;

                    return (
                      <div key={u.id} className="space-y-3 p-4">
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0 space-y-0.5">
                            <div className="flex flex-wrap items-center gap-1.5">
                              <span className="font-medium text-foreground break-words">
                                {u.full_name}
                              </span>
                              {isSelf && (
                                <span className="ui-tag">
                                  {t.prod.company.youBadge}
                                </span>
                              )}
                            </div>
                            <div className="font-mono text-xs text-muted-foreground">
                              {u.login}
                            </div>
                          </div>
                          <span
                            className={cn(
                              "ui-status shrink-0",
                              !u.is_active && "text-[var(--status-neutral-text)]"
                            )}
                          >
                            <span
                              aria-hidden="true"
                              className={cn(
                                "ui-status-dot",
                                u.is_active ? "ui-dot-ok" : "ui-dot-neutral"
                              )}
                            />
                            <span>
                              {u.is_active
                                ? t.prod.company.activeStatus
                                : t.prod.company.inactiveStatus}
                            </span>
                          </span>
                        </div>

                        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground tabular-nums">
                          <span>
                            {t.prod.company.colCreated}:{" "}
                            {formatDate(u.created_at)}
                          </span>
                          {!isDirector && (
                            <span className="ui-tag">
                              {t.prod.roles[u.role]}
                            </span>
                          )}
                        </div>

                        {isDirector && (
                          <div className="flex flex-col gap-2 pt-1 sm:flex-row sm:items-center">
                            <select
                              aria-label={`${t.prod.company.colRole}: ${u.login}`}
                              value={u.role}
                              disabled={isBusy || protectedLastDir}
                              onChange={(e) =>
                                void handleUpdateUser(u, {
                                  role: e.target.value as CompanyRole,
                                })
                              }
                              className="ui-select disabled:opacity-60"
                            >
                              <option value="accountant">
                                {t.prod.roles.accountant}
                              </option>
                              <option value="director">
                                {t.prod.roles.director}
                              </option>
                            </select>

                            <Button
                              type="button"
                              variant={u.is_active ? "destructive" : "outline"}
                              size="sm"
                              disabled={
                                isBusy || (u.is_active && protectedLastDir)
                              }
                              onClick={() =>
                                void handleUpdateUser(u, {
                                  is_active: !u.is_active,
                                })
                              }
                              className="min-h-10 sm:min-h-8"
                            >
                              {isBusy && (
                                <Loader2 className="size-3.5 animate-spin" />
                              )}
                              <span>
                                {u.is_active
                                  ? t.prod.company.deactivateButton
                                  : t.prod.company.activateButton}
                              </span>
                            </Button>

                            {protectedLastDir && (
                              <span className="text-[11px] text-muted-foreground">
                                {t.prod.company.lastDirectorHint}
                              </span>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>

                {/* Desktop table (>= md) */}
                <div className="hidden overflow-x-auto md:block">
                  <Table>
                    <TableHeader>
                      <TableRow className="hover:bg-transparent">
                        <TableHead className="pl-4">
                          {t.prod.company.colUser}
                        </TableHead>
                        <TableHead className="w-[160px]">
                          {t.prod.company.colLogin}
                        </TableHead>
                        <TableHead className="w-[180px]">
                          {t.prod.company.colRole}
                        </TableHead>
                        <TableHead className="w-[125px]">
                          {t.prod.company.colStatus}
                        </TableHead>
                        <TableHead className="w-[130px]">
                          {t.prod.company.colCreated}
                        </TableHead>
                        {isDirector && (
                          <TableHead className="w-[175px] pr-4 text-right">
                            {t.prod.company.colActions}
                          </TableHead>
                        )}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {company.users.map((u) => {
                        const isSelf = u.id === session?.user.id;
                        const protectedLastDir = isLastActiveDirector(u);
                        const isBusy = updatingUserId === u.id;

                        return (
                          <TableRow key={u.id}>
                            <TableCell className="pl-4 py-2.5">
                              <div className="flex flex-wrap items-center gap-1.5">
                                <span className="font-medium text-foreground break-words">
                                  {u.full_name}
                                </span>
                                {isSelf && (
                                  <span className="ui-tag">
                                    {t.prod.company.youBadge}
                                  </span>
                                )}
                              </div>
                            </TableCell>
                            <TableCell className="py-2.5 font-mono text-xs text-muted-foreground">
                              {u.login}
                            </TableCell>
                            <TableCell className="py-2.5">
                              {isDirector ? (
                                <div className="space-y-1">
                                  <select
                                    aria-label={`${t.prod.company.colRole}: ${u.login}`}
                                    value={u.role}
                                    disabled={isBusy || protectedLastDir}
                                    title={
                                      protectedLastDir
                                        ? t.prod.company.lastDirectorHint
                                        : undefined
                                    }
                                    onChange={(e) =>
                                      void handleUpdateUser(u, {
                                        role: e.target.value as CompanyRole,
                                      })
                                    }
                                    className="ui-select h-8 text-xs disabled:cursor-not-allowed disabled:opacity-60"
                                  >
                                    <option value="accountant">
                                      {t.prod.roles.accountant}
                                    </option>
                                    <option value="director">
                                      {t.prod.roles.director}
                                    </option>
                                  </select>
                                  {protectedLastDir && (
                                    <div className="text-[11px] text-muted-foreground">
                                      {t.prod.company.lastDirectorHint}
                                    </div>
                                  )}
                                </div>
                              ) : (
                                <span className="text-sm text-foreground">
                                  {t.prod.roles[u.role]}
                                </span>
                              )}
                            </TableCell>
                            <TableCell className="py-2.5">
                              <span
                                className={cn(
                                  "ui-status",
                                  !u.is_active &&
                                    "text-[var(--status-neutral-text)]"
                                )}
                              >
                                <span
                                  aria-hidden="true"
                                  className={cn(
                                    "ui-status-dot",
                                    u.is_active ? "ui-dot-ok" : "ui-dot-neutral"
                                  )}
                                />
                                <span>
                                  {u.is_active
                                    ? t.prod.company.activeStatus
                                    : t.prod.company.inactiveStatus}
                                </span>
                              </span>
                            </TableCell>
                            <TableCell className="py-2.5 text-xs tabular-nums text-muted-foreground whitespace-nowrap">
                              {formatDate(u.created_at)}
                            </TableCell>
                            {isDirector && (
                              <TableCell className="pr-4 py-2.5 text-right">
                                <Button
                                  type="button"
                                  variant={
                                    u.is_active ? "destructive" : "outline"
                                  }
                                  size="sm"
                                  disabled={
                                    isBusy || (u.is_active && protectedLastDir)
                                  }
                                  title={
                                    u.is_active && protectedLastDir
                                      ? t.prod.company.lastDirectorHint
                                      : undefined
                                  }
                                  onClick={() =>
                                    void handleUpdateUser(u, {
                                      is_active: !u.is_active,
                                    })
                                  }
                                  className="h-8 text-xs"
                                >
                                  {isBusy && (
                                    <Loader2 className="size-3.5 animate-spin" />
                                  )}
                                  <span>
                                    {u.is_active
                                      ? t.prod.company.deactivateButton
                                      : t.prod.company.activateButton}
                                  </span>
                                </Button>
                              </TableCell>
                            )}
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>
          </>
        )
      )}

      {/* Invite user dialog (director-only, displays temporary password ONCE) */}
      {isDirector && (
        <Dialog open={inviteOpen} onOpenChange={closeInviteDialog}>
          <DialogContent mobileSheet className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>
                {inviteResult
                  ? t.prod.company.inviteDialog.successTitle
                  : t.prod.company.inviteDialog.title}
              </DialogTitle>
              {!inviteResult && (
                <DialogDescription>
                  {t.prod.company.inviteDialog.description}
                </DialogDescription>
              )}
            </DialogHeader>

            {inviteResult ? (
              <div className="space-y-4">
                <div
                  role="alert"
                  className="ui-notice ui-notice-warn text-xs leading-relaxed text-foreground break-words"
                >
                  {t.prod.company.inviteDialog.tempPasswordWarning}
                </div>

                <div className="ui-subpanel space-y-3">
                  <div className="space-y-0.5 text-xs">
                    <div className="text-muted-foreground">
                      {t.prod.company.inviteDialog.loginLabel}
                    </div>
                    <div className="font-mono text-sm font-semibold text-foreground">
                      {inviteResult.user.login}
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <Label htmlFor="invite-temp-password" className="text-xs">
                      {t.prod.company.inviteDialog.tempPasswordLabel}
                    </Label>
                    <div className="flex items-center gap-2">
                      <Input
                        id="invite-temp-password"
                        type="text"
                        readOnly
                        value={inviteResult.temporary_password}
                        onFocus={(e) => e.currentTarget.select()}
                        className="h-10 rounded-[6px] bg-card font-mono text-sm font-medium sm:h-9"
                      />
                      <Button
                        type="button"
                        variant="outline"
                        onClick={() => void handleCopyTempPassword()}
                        className="h-10 shrink-0 gap-1.5 px-3 sm:h-9"
                      >
                        {copiedPassword ? (
                          <>
                            <Check className="size-4 text-[var(--status-ok-text)]" />
                            <span>{t.prod.company.inviteDialog.copied}</span>
                          </>
                        ) : (
                          <>
                            <Copy className="size-4" />
                            <span>
                              {t.prod.company.inviteDialog.copyCredentials}
                            </span>
                          </>
                        )}
                      </Button>
                    </div>
                  </div>
                </div>

                <DialogFooter>
                  <Button
                    type="button"
                    onClick={() => closeInviteDialog(false)}
                    className="min-h-11 w-full sm:min-h-9 sm:w-auto"
                  >
                    {t.prod.company.inviteDialog.doneButton}
                  </Button>
                </DialogFooter>
              </div>
            ) : (
              <form onSubmit={handleInviteSubmit} className="space-y-4">
                {inviteError && (
                  <Alert variant="destructive">
                    <AlertCircle className="size-4" />
                    <AlertDescription className="break-words">
                      {inviteError}
                    </AlertDescription>
                  </Alert>
                )}

                <div className="space-y-1.5">
                  <Label htmlFor="invite-login">
                    {t.prod.company.inviteDialog.loginLabel}
                  </Label>
                  <Input
                    id="invite-login"
                    type="text"
                    required
                    minLength={3}
                    maxLength={64}
                    autoFocus
                    placeholder={t.prod.company.inviteDialog.loginPlaceholder}
                    value={inviteLogin}
                    onChange={(e) => {
                      setInviteLogin(e.target.value);
                      if (inviteError) setInviteError(null);
                    }}
                    disabled={isInviting}
                    className="h-10 rounded-[6px] font-mono sm:h-9"
                  />
                  <p className="text-xs text-muted-foreground">
                    {t.prod.company.inviteDialog.loginHint}
                  </p>
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="invite-full-name">
                    {t.prod.company.inviteDialog.fullNameLabel}
                  </Label>
                  <Input
                    id="invite-full-name"
                    type="text"
                    required
                    maxLength={120}
                    placeholder={t.prod.company.inviteDialog.fullNamePlaceholder}
                    value={inviteFullName}
                    onChange={(e) => {
                      setInviteFullName(e.target.value);
                      if (inviteError) setInviteError(null);
                    }}
                    disabled={isInviting}
                    className="h-10 rounded-[6px] sm:h-9"
                  />
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="invite-role">
                    {t.prod.company.inviteDialog.roleLabel}
                  </Label>
                  <select
                    id="invite-role"
                    value={inviteRole}
                    onChange={(e) =>
                      setInviteRole(e.target.value as CompanyRole)
                    }
                    disabled={isInviting}
                    className="ui-select w-full"
                  >
                    <option value="accountant">{t.prod.roles.accountant}</option>
                    <option value="director">{t.prod.roles.director}</option>
                  </select>
                </div>

                <DialogFooter>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => closeInviteDialog(false)}
                    disabled={isInviting}
                    className="min-h-11 w-full sm:min-h-9 sm:w-auto"
                  >
                    {t.common.cancel}
                  </Button>
                  <Button
                    type="submit"
                    disabled={
                      isInviting ||
                      !inviteLogin.trim() ||
                      !inviteFullName.trim()
                    }
                    className="min-h-11 w-full sm:min-h-9 sm:w-auto"
                  >
                    {isInviting ? (
                      <>
                        <Loader2 className="size-4 animate-spin" />
                        <span>{t.prod.company.inviteDialog.submitting}</span>
                      </>
                    ) : (
                      <span>{t.prod.company.inviteDialog.submit}</span>
                    )}
                  </Button>
                </DialogFooter>
              </form>
            )}
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}

export default function ProdCompanyPage() {
  return (
    <RequireRole roles={["accountant", "director"]}>
      <CompanyPageContent />
    </RequireRole>
  );
}
