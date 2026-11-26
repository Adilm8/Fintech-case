"use client";

import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { ArrowLeft, ArrowRight, ChevronDown, Loader2 } from "lucide-react";
import { AdviceBox } from "@/components/AdviceBox";
import { useAppData } from "@/components/AppShell";
import { ReasonsList } from "@/components/ReasonsList";
import { VerdictBadge } from "@/components/VerdictBadge";
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
import { useT } from "@/i18n";
import {
  checkPayment,
  getErrorMessage,
  isNetworkUnreachableError,
} from "@/lib/api";
import {
  applyBccOtherCompanyAttack,
  applyHomoglyphAttack,
  applyInvisibleCharAttack,
  applyMultiplyAmountAttack,
  applyOtherBankIikAttack,
  applyOwnBinOwnAccountAttack,
  applyUrgentPurposeAttack,
} from "@/lib/attacks";
import { computeAlignedCharDiff } from "@/lib/diff";
import { pickActionText, pickHeadline } from "@/lib/format";
import { notify } from "@/lib/toast";
import type { CheckRequest, CheckResult, QueueItem } from "@/lib/types";
import { cn } from "cn";

interface AttackFormState {
  recipient_name: string;
  recipient_bin: string;
  recipient_iik: string;
  recipient_bik: string;
  amount_kzt: string;
  purpose: string;
  kbe: string;
  knp: string;
}

const DEFAULT_KBE = "17";
const DEFAULT_KNP = "710";

function requestToForm(req: CheckRequest): AttackFormState {
  return {
    recipient_name: req.recipient_name,
    recipient_bin: req.recipient_bin,
    recipient_iik: req.recipient_iik,
    recipient_bik: req.recipient_bik,
    amount_kzt: String(req.amount_kzt),
    purpose: req.purpose,
    kbe: req.kbe?.trim() || DEFAULT_KBE,
    knp: req.knp?.trim() || DEFAULT_KNP,
  };
}

function parseAmount(raw: string): number {
  const cleaned = raw.replace(/\s+/g, "").replace(",", ".");
  if (!cleaned) return Number.NaN;
  return Number(cleaned);
}

function formToRequest(
  form: AttackFormState,
  payerId?: string
): CheckRequest | null {
  const recipient_name = form.recipient_name.trim();
  const recipient_bin = form.recipient_bin.replace(/\s+/g, "");
  const recipient_iik = form.recipient_iik.replace(/\s+/g, "").toUpperCase();
  const recipient_bik = form.recipient_bik.replace(/\s+/g, "").toUpperCase();
  const purpose = form.purpose.trim();
  const kbe = form.kbe.replace(/\D+/g, "").slice(0, 2);
  const knp = form.knp.replace(/\D+/g, "").slice(0, 3);
  const amount_kzt = parseAmount(form.amount_kzt);

  if (
    !recipient_name ||
    !recipient_bin ||
    !recipient_iik ||
    !recipient_bik ||
    !purpose ||
    !Number.isFinite(amount_kzt) ||
    amount_kzt <= 0
  ) {
    return null;
  }

  return {
    ...(payerId !== undefined ? { payer_id: payerId } : {}),
    recipient_name,
    recipient_bin,
    recipient_iik,
    recipient_bik,
    amount_kzt,
    purpose,
    ...(kbe ? { kbe } : {}),
    ...(knp ? { knp } : {}),
  };
}

function formsDiffer(a: AttackFormState, b: AttackFormState): boolean {
  return (
    a.recipient_name !== b.recipient_name ||
    a.recipient_bin !== b.recipient_bin ||
    a.recipient_iik !== b.recipient_iik ||
    a.recipient_bik !== b.recipient_bik ||
    a.amount_kzt !== b.amount_kzt ||
    a.purpose !== b.purpose ||
    a.kbe !== b.kbe ||
    a.knp !== b.knp
  );
}

function CharDiffHighlight({
  original,
  attacked,
  monospace = false,
}: {
  original: string;
  attacked: string;
  monospace?: boolean;
}) {
  const { t, interpolate } = useT();
  const tokens = useMemo(
    () => computeAlignedCharDiff(original, attacked),
    [original, attacked]
  );

  if (tokens.length === 0) {
    return <span className="text-muted-foreground">—</span>;
  }

  return (
    <span
      className={cn(
        monospace
          ? "font-mono text-xs tabular-nums sm:text-sm break-all [overflow-wrap:anywhere]"
          : "text-sm leading-relaxed break-words [overflow-wrap:anywhere]"
      )}
    >
      {tokens.map((token, idx) => {
        const allowBreak = monospace && idx < tokens.length - 1;
        if (!token.changed) {
          return (
            <Fragment key={idx}>
              <span>{token.char}</span>
              {allowBreak && <wbr />}
            </Fragment>
          );
        }

        const tooltipText = token.isInvisible
          ? interpolate(t.attack.codePointInvisibleTooltip, {
              curr: token.codePoint,
            })
          : token.originalCodePoint
            ? interpolate(
                token.isHomoglyphLookalike
                  ? t.attack.codePointHomoglyphTooltip
                  : t.attack.codePointSwapTooltip,
                {
                  orig: token.originalCodePoint,
                  curr: token.codePoint,
                }
              )
            : interpolate(t.attack.codePointAddedTooltip, {
                curr: token.codePoint,
              });

        const isAlertHighlight = token.isHomoglyphLookalike || token.isInvisible;

        return (
          <Fragment key={idx}>
            <mark
              title={tooltipText}
              aria-label={tooltipText}
              className={isAlertHighlight ? "ui-mark-danger" : "ui-mark-warn"}
            >
              {token.isInvisible ? (
                <>
                  <span className="font-mono text-[11px] leading-none">
                    {token.codePoint}
                  </span>
                  <span className="ui-mark-tag">{t.attack.invisibleTag}</span>
                </>
              ) : (
                <>
                  <span>
                    {token.char === " " ? "\u00A0" : token.char}
                  </span>
                  {token.isHomoglyphLookalike && (
                    <span className="ui-mark-tag">{t.comparison.latinTag}</span>
                  )}
                </>
              )}
            </mark>
            {allowBreak && <wbr />}
          </Fragment>
        );
      })}
    </span>
  );
}

interface AttackWorkspaceProps {
  baseItem: QueueItem;
  onNetworkError: (message: string) => void;
}

function AttackWorkspace({ baseItem, onNetworkError }: AttackWorkspaceProps) {
  const { t, lang, formatMoney, interpolate } = useT();

  const originalForm = useMemo(
    () => requestToForm(baseItem.request),
    [baseItem.request]
  );

  const [attackedForm, setAttackedForm] = useState<AttackFormState>(
    () => originalForm
  );
  const [liveResult, setLiveResult] = useState<CheckResult | null>(null);
  const [isChecking, setIsChecking] = useState(false);
  const [checkError, setCheckError] = useState<string | null>(null);

  const requestSeqRef = useRef(0);
  const onNetworkErrorRef = useRef(onNetworkError);

  useEffect(() => {
    onNetworkErrorRef.current = onNetworkError;
  }, [onNetworkError]);

  const isDirty = formsDiffer(originalForm, attackedForm);
  const parsedPayload = useMemo(
    () => formToRequest(attackedForm, baseItem.request.payer_id),
    [attackedForm, baseItem.request.payer_id]
  );

  useEffect(() => {
    if (!isDirty || !parsedPayload) {
      return;
    }

    const seq = requestSeqRef.current + 1;
    requestSeqRef.current = seq;
    let controller: AbortController | null = null;

    const timer = window.setTimeout(() => {
      controller = new AbortController();
      setIsChecking(true);
      setCheckError(null);

      checkPayment(parsedPayload, lang, {
        signal: controller.signal,
        historyAction: "attack_sim",
      })
        .then((res) => {
          if (requestSeqRef.current !== seq) return;
          setLiveResult(res);
          setCheckError(null);
        })
        .catch((err) => {
          if (err instanceof DOMException && err.name === "AbortError") {
            return;
          }
          if (requestSeqRef.current !== seq) return;
          const message = getErrorMessage(err);
          setCheckError(message);
          if (isNetworkUnreachableError(err)) {
            onNetworkErrorRef.current(message);
            notify.error(t.common.serverErrorTitle, message);
          } else {
            notify.error(t.attack.checkErrorTitle, message);
          }
        })
        .finally(() => {
          if (requestSeqRef.current === seq) {
            setIsChecking(false);
          }
        });
    }, 300);

    return () => {
      window.clearTimeout(timer);
      controller?.abort();
    };
  }, [
    isDirty,
    parsedPayload,
    lang,
    t.attack.checkErrorTitle,
    t.common.serverErrorTitle,
  ]);

  const effectiveResult: CheckResult = isDirty
    ? liveResult ?? baseItem.result
    : baseItem.result;

  const originalVerdict = baseItem.result.verdict;
  const attackedVerdict = effectiveResult.verdict;
  const verdictChanged = isDirty && attackedVerdict !== originalVerdict;

  const buildAttackBaseRequest = (): CheckRequest => {
    const cleanKbe = attackedForm.kbe.replace(/\D+/g, "").slice(0, 2);
    const cleanKnp = attackedForm.knp.replace(/\D+/g, "").slice(0, 3);
    return {
      ...(baseItem.request.payer_id !== undefined
        ? { payer_id: baseItem.request.payer_id }
        : {}),
      recipient_name: attackedForm.recipient_name,
      recipient_bin: attackedForm.recipient_bin,
      recipient_iik: attackedForm.recipient_iik,
      recipient_bik: attackedForm.recipient_bik,
      amount_kzt: Number.isFinite(parseAmount(attackedForm.amount_kzt))
        ? parseAmount(attackedForm.amount_kzt)
        : baseItem.request.amount_kzt,
      purpose: attackedForm.purpose,
      ...(cleanKbe ? { kbe: cleanKbe } : {}),
      ...(cleanKnp ? { knp: cleanKnp } : {}),
    };
  };

  const applyAttack = (fn: (req: CheckRequest) => CheckRequest) => {
    const currentReq = buildAttackBaseRequest();
    const nextReq = fn(currentReq);
    setAttackedForm(requestToForm(nextReq));
    setCheckError(null);
  };

  const handleHomoglyphClick = () => {
    const currentReq = buildAttackBaseRequest();
    const nextReq = applyHomoglyphAttack(currentReq);
    if (nextReq.recipient_name === currentReq.recipient_name) {
      notify.info(t.attack.btnHomoglyph, t.attack.noHomoglyphLeft);
      return;
    }
    setAttackedForm(requestToForm(nextReq));
    setCheckError(null);
  };

  const handleInvisibleCharClick = () => {
    const currentReq = buildAttackBaseRequest();
    const nextReq = applyInvisibleCharAttack(currentReq);
    if (nextReq.recipient_name === currentReq.recipient_name) {
      notify.info(
        t.attack.btnInvisibleChar,
        t.attack.invisibleCharAlreadyPresent
      );
      return;
    }
    setAttackedForm(requestToForm(nextReq));
    setCheckError(null);
  };

  const handleReset = () => {
    requestSeqRef.current += 1;
    setAttackedForm(originalForm);
    setLiveResult(null);
    setCheckError(null);
    setIsChecking(false);
  };

  const updateField = (field: keyof AttackFormState, rawValue: string) => {
    let value = rawValue;
    if (field === "kbe") {
      value = rawValue.replace(/\D+/g, "").slice(0, 2);
    } else if (field === "knp") {
      value = rawValue.replace(/\D+/g, "").slice(0, 3);
    }
    setAttackedForm((prev) => ({ ...prev, [field]: value }));
    if (checkError) setCheckError(null);
  };

  const allFields: {
    key: keyof AttackFormState;
    label: string;
    original: string;
    attacked: string;
    monospace?: boolean;
  }[] = [
    {
      key: "recipient_name",
      label: t.fields.name,
      original: originalForm.recipient_name,
      attacked: attackedForm.recipient_name,
    },
    {
      key: "recipient_bin",
      label: t.fields.bin,
      original: originalForm.recipient_bin,
      attacked: attackedForm.recipient_bin,
      monospace: true,
    },
    {
      key: "recipient_iik",
      label: t.fields.iik,
      original: originalForm.recipient_iik,
      attacked: attackedForm.recipient_iik,
      monospace: true,
    },
    {
      key: "recipient_bik",
      label: t.fields.bik,
      original: originalForm.recipient_bik,
      attacked: attackedForm.recipient_bik,
      monospace: true,
    },
    {
      key: "amount_kzt",
      label: t.fields.amount,
      original: formatMoney(baseItem.request.amount_kzt),
      attacked: Number.isFinite(parseAmount(attackedForm.amount_kzt))
        ? formatMoney(parseAmount(attackedForm.amount_kzt))
        : attackedForm.amount_kzt,
    },
    {
      key: "kbe",
      label: t.attack.kbeLabel,
      original: originalForm.kbe,
      attacked: attackedForm.kbe,
      monospace: true,
    },
    {
      key: "knp",
      label: t.attack.knpLabel,
      original: originalForm.knp,
      attacked: attackedForm.knp,
      monospace: true,
    },
    {
      key: "purpose",
      label: t.attack.purposeLabel,
      original: originalForm.purpose,
      attacked: attackedForm.purpose,
    },
  ];
  const changedFields = allFields.filter(
    (entry) => entry.original !== entry.attacked
  );

  return (
    <div className="space-y-4 sm:space-y-5">
      {/* Quick Attack Buttons + Editable Attacked Fields */}
      <Card className="min-w-0">
        <CardHeader className="space-y-3 border-b border-border pb-3.5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <CardTitle>{t.attack.quickAttacksTitle}</CardTitle>
              <CardDescription className="mt-0.5">
                {t.attack.editableFieldsHint}
              </CardDescription>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleReset}
              disabled={!isDirty}
              className="min-h-10 sm:min-h-8"
            >
              {t.attack.btnReset}
            </Button>
          </div>

          <div className="flex flex-wrap gap-1.5">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleHomoglyphClick}
              className="min-h-10 sm:min-h-8"
            >
              {t.attack.btnHomoglyph}
            </Button>

            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleInvisibleCharClick}
              className="min-h-10 sm:min-h-8"
            >
              {t.attack.btnInvisibleChar}
            </Button>

            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => applyAttack(applyOtherBankIikAttack)}
              className="min-h-10 sm:min-h-8"
            >
              {t.attack.btnOtherBank}
            </Button>

            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => applyAttack(applyOwnBinOwnAccountAttack)}
              className="min-h-10 sm:min-h-8"
            >
              {t.attack.btnOwnBinOwnAccount}
            </Button>

            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => applyAttack(applyBccOtherCompanyAttack)}
              className="min-h-10 sm:min-h-8"
            >
              {t.attack.btnBccOtherCompany}
            </Button>

            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() =>
                applyAttack((req) => applyMultiplyAmountAttack(req, 4))
              }
              className="min-h-10 sm:min-h-8"
            >
              {t.attack.btnAmount4x}
            </Button>

            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => applyAttack(applyUrgentPurposeAttack)}
              className="min-h-10 sm:min-h-8"
            >
              {t.attack.btnAddUrgent}
            </Button>
          </div>
        </CardHeader>

        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2 lg:grid-cols-3">
            <div className="min-w-0 space-y-1.5 sm:col-span-2 lg:col-span-2">
              <div className="flex items-center justify-between gap-2">
                <Label htmlFor="attack_recipient_name">
                  {t.queue.labelRecipientName}
                </Label>
                {attackedForm.recipient_name !== originalForm.recipient_name && (
                  <span className="text-[11px] text-muted-foreground">
                    {t.attack.modifiedBadge}
                  </span>
                )}
              </div>
              <Input
                id="attack_recipient_name"
                value={attackedForm.recipient_name}
                onChange={(e) => updateField("recipient_name", e.target.value)}
                className="h-10 bg-card sm:h-9"
              />
              {attackedForm.recipient_name !== originalForm.recipient_name && (
                <div className="rounded-[6px] border border-border bg-muted/40 px-2.5 py-1.5">
                  <CharDiffHighlight
                    original={originalForm.recipient_name}
                    attacked={attackedForm.recipient_name}
                  />
                </div>
              )}
            </div>

            <div className="min-w-0 space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <Label htmlFor="attack_amount_kzt">{t.queue.labelAmount}</Label>
                {attackedForm.amount_kzt !== originalForm.amount_kzt && (
                  <span className="text-[11px] text-muted-foreground">
                    {t.attack.modifiedBadge}
                  </span>
                )}
              </div>
              <Input
                id="attack_amount_kzt"
                type="number"
                min="1"
                step="any"
                value={attackedForm.amount_kzt}
                onChange={(e) => updateField("amount_kzt", e.target.value)}
                className="h-10 bg-card tabular-nums sm:h-9"
              />
            </div>

            <div className="min-w-0 space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <Label htmlFor="attack_recipient_bin">{t.queue.labelBin}</Label>
                {attackedForm.recipient_bin !== originalForm.recipient_bin && (
                  <span className="text-[11px] text-muted-foreground">
                    {t.attack.modifiedBadge}
                  </span>
                )}
              </div>
              <Input
                id="attack_recipient_bin"
                inputMode="numeric"
                value={attackedForm.recipient_bin}
                onChange={(e) => updateField("recipient_bin", e.target.value)}
                className="h-10 bg-card font-mono tabular-nums sm:h-9"
              />
              {attackedForm.recipient_bin !== originalForm.recipient_bin && (
                <div className="rounded-[6px] border border-border bg-muted/40 px-2.5 py-1.5">
                  <CharDiffHighlight
                    original={originalForm.recipient_bin}
                    attacked={attackedForm.recipient_bin}
                    monospace
                  />
                </div>
              )}
            </div>

            <div className="min-w-0 space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <Label htmlFor="attack_recipient_iik">{t.queue.labelIik}</Label>
                {attackedForm.recipient_iik !== originalForm.recipient_iik && (
                  <span className="text-[11px] text-muted-foreground">
                    {t.attack.modifiedBadge}
                  </span>
                )}
              </div>
              <Input
                id="attack_recipient_iik"
                value={attackedForm.recipient_iik}
                onChange={(e) => updateField("recipient_iik", e.target.value)}
                className="h-10 bg-card font-mono uppercase tabular-nums sm:h-9"
              />
              {attackedForm.recipient_iik !== originalForm.recipient_iik && (
                <div className="rounded-[6px] border border-border bg-muted/40 px-2.5 py-1.5">
                  <CharDiffHighlight
                    original={originalForm.recipient_iik}
                    attacked={attackedForm.recipient_iik}
                    monospace
                  />
                </div>
              )}
            </div>

            <div className="min-w-0 space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <Label htmlFor="attack_recipient_bik">{t.queue.labelBik}</Label>
                {attackedForm.recipient_bik !== originalForm.recipient_bik && (
                  <span className="text-[11px] text-muted-foreground">
                    {t.attack.modifiedBadge}
                  </span>
                )}
              </div>
              <Input
                id="attack_recipient_bik"
                value={attackedForm.recipient_bik}
                onChange={(e) => updateField("recipient_bik", e.target.value)}
                className="h-10 bg-card font-mono uppercase tabular-nums sm:h-9"
              />
              {attackedForm.recipient_bik !== originalForm.recipient_bik && (
                <div className="rounded-[6px] border border-border bg-muted/40 px-2.5 py-1.5">
                  <CharDiffHighlight
                    original={originalForm.recipient_bik}
                    attacked={attackedForm.recipient_bik}
                    monospace
                  />
                </div>
              )}
            </div>

            <div className="min-w-0 space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <Label htmlFor="attack_kbe">{t.queue.labelKbe}</Label>
                {attackedForm.kbe !== originalForm.kbe && (
                  <span className="text-[11px] text-muted-foreground">
                    {t.attack.modifiedBadge}
                  </span>
                )}
              </div>
              <Input
                id="attack_kbe"
                inputMode="numeric"
                maxLength={2}
                placeholder={t.queue.placeholderKbe}
                value={attackedForm.kbe}
                onChange={(e) => updateField("kbe", e.target.value)}
                className="h-10 bg-card font-mono tabular-nums sm:h-9"
              />
            </div>

            <div className="min-w-0 space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <Label htmlFor="attack_knp">{t.queue.labelKnp}</Label>
                {attackedForm.knp !== originalForm.knp && (
                  <span className="text-[11px] text-muted-foreground">
                    {t.attack.modifiedBadge}
                  </span>
                )}
              </div>
              <Input
                id="attack_knp"
                inputMode="numeric"
                maxLength={3}
                placeholder={t.queue.placeholderKnp}
                value={attackedForm.knp}
                onChange={(e) => updateField("knp", e.target.value)}
                className="h-10 bg-card font-mono tabular-nums sm:h-9"
              />
            </div>

            <div className="min-w-0 space-y-1.5 sm:col-span-2 lg:col-span-3">
              <div className="flex items-center justify-between gap-2">
                <Label htmlFor="attack_purpose">{t.queue.labelPurpose}</Label>
                {attackedForm.purpose !== originalForm.purpose && (
                  <span className="text-[11px] text-muted-foreground">
                    {t.attack.modifiedBadge}
                  </span>
                )}
              </div>
              <Input
                id="attack_purpose"
                value={attackedForm.purpose}
                onChange={(e) => updateField("purpose", e.target.value)}
                className="h-10 bg-card sm:h-9"
              />
              {attackedForm.purpose !== originalForm.purpose && (
                <div className="rounded-[6px] border border-border bg-muted/40 px-2.5 py-1.5">
                  <CharDiffHighlight
                    original={originalForm.purpose}
                    attacked={attackedForm.purpose}
                  />
                </div>
              )}
            </div>
          </div>

          {isDirty && !parsedPayload && (
            <div
              role="status"
              className="ui-notice ui-notice-warn py-2 text-xs text-foreground"
            >
              {t.attack.incompleteHint}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Verdict transition indicator */}
      {verdictChanged && (
        <div
          role="status"
          className="ui-notice ui-notice-danger flex flex-wrap items-center justify-between gap-3"
        >
          <div className="flex flex-wrap items-center gap-2.5">
            <span className="text-sm font-semibold text-foreground">
              {t.attack.verdictChangedTitle}:
            </span>
            <VerdictBadge verdict={originalVerdict} />
            <ArrowRight className="size-4 shrink-0 text-muted-foreground" />
            <VerdictBadge verdict={attackedVerdict} />
          </div>
          <div className="font-mono text-xs font-medium text-foreground tabular-nums">
            {baseItem.result.score} → {effectiveResult.score} / 100
          </div>
        </div>
      )}

      {/* Side-by-side comparison: stacked on phones/tablets, 2 columns on lg+ */}
      <div className="grid grid-cols-1 items-start gap-4 sm:gap-5 lg:grid-cols-2">
        {/* Left Card: Original */}
        <Card className="min-w-0">
          <CardHeader className="border-b border-border pb-3.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <CardTitle>{t.attack.originalCardTitle}</CardTitle>
              <VerdictBadge verdict={baseItem.result.verdict} />
            </div>
            <CardDescription className="mt-1 flex flex-wrap items-center justify-between gap-2">
              <span className="break-words">
                {pickHeadline(baseItem.result, lang)}
              </span>
              <span className="shrink-0 font-mono text-xs font-medium text-foreground tabular-nums">
                {interpolate(t.attack.scoreLabel, {
                  score: baseItem.result.score,
                })}
              </span>
            </CardDescription>
          </CardHeader>

          <CardContent>
            <dl className="ui-dl">
              <div className="ui-dl-row">
                <dt className="ui-dt">{t.fields.name}</dt>
                <dd className="ui-dd font-medium">
                  {baseItem.request.recipient_name}
                </dd>
              </div>
              <div className="ui-dl-row">
                <dt className="ui-dt">{t.fields.bin}</dt>
                <dd className="ui-dd font-mono tabular-nums">
                  {baseItem.request.recipient_bin}
                </dd>
              </div>
              <div className="ui-dl-row">
                <dt className="ui-dt">{t.fields.iik}</dt>
                <dd className="ui-dd font-mono tabular-nums break-all">
                  {baseItem.request.recipient_iik}
                </dd>
              </div>
              <div className="ui-dl-row">
                <dt className="ui-dt">{t.fields.bik}</dt>
                <dd className="ui-dd font-mono tabular-nums">
                  {baseItem.request.recipient_bik}
                </dd>
              </div>
              <div className="ui-dl-row">
                <dt className="ui-dt">{t.fields.amount}</dt>
                <dd className="ui-dd font-medium tabular-nums whitespace-nowrap">
                  {formatMoney(baseItem.request.amount_kzt)}
                </dd>
              </div>
              <div className="ui-dl-row">
                <dt className="ui-dt">{t.attack.kbeLabel}</dt>
                <dd className="ui-dd font-mono tabular-nums">
                  {originalForm.kbe || "—"}
                </dd>
              </div>
              <div className="ui-dl-row">
                <dt className="ui-dt">{t.attack.knpLabel}</dt>
                <dd className="ui-dd font-mono tabular-nums">
                  {originalForm.knp || "—"}
                </dd>
              </div>
              <div className="ui-dl-row">
                <dt className="ui-dt">{t.attack.purposeLabel}</dt>
                <dd className="ui-dd">{baseItem.request.purpose}</dd>
              </div>
            </dl>
          </CardContent>
        </Card>

        {/* Right Card: After Attack (live) */}
        <Card
          className={cn(
            "min-w-0 transition-opacity",
            isChecking && "opacity-85"
          )}
        >
          <CardHeader className="border-b border-border pb-3.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <CardTitle>{t.attack.attackedCardTitle}</CardTitle>
                <span
                  aria-live="polite"
                  className={cn(
                    "inline-flex items-center gap-1 text-xs text-muted-foreground transition-opacity",
                    isChecking
                      ? "opacity-100"
                      : "pointer-events-none opacity-0"
                  )}
                >
                  <Loader2 className="size-3 animate-spin" aria-hidden="true" />
                  <span>{t.attack.checkingLive}</span>
                </span>
              </div>
              <VerdictBadge verdict={effectiveResult.verdict} />
            </div>

            <CardDescription className="mt-1 flex flex-wrap items-center justify-between gap-2">
              <span className="font-medium text-foreground break-words">
                {pickHeadline(effectiveResult, lang)}
              </span>
              <span className="shrink-0 font-mono text-xs font-medium text-foreground tabular-nums">
                {interpolate(t.attack.scoreLabel, {
                  score: effectiveResult.score,
                })}
              </span>
            </CardDescription>
          </CardHeader>

          <CardContent className="space-y-4">
            {checkError && (
              <div
                role="alert"
                className="ui-notice ui-notice-danger space-y-0.5"
              >
                <div className="text-[13px] font-semibold text-[var(--status-danger-text)]">
                  {t.attack.checkErrorTitle}
                </div>
                <p className="text-xs text-foreground break-words">
                  {checkError}
                </p>
              </div>
            )}

            {/* Highlighted character diffs */}
            <div className="ui-subpanel space-y-2">
              <div className="ui-label-meta">{t.attack.diffPreviewTitle}</div>
              {changedFields.length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  {t.attack.noFieldChanges}
                </p>
              ) : (
                <div className="space-y-2">
                  {changedFields.map((entry) => (
                    <div key={entry.key} className="space-y-0.5">
                      <div className="text-xs font-medium text-muted-foreground">
                        {entry.label}
                      </div>
                      <div>
                        <CharDiffHighlight
                          original={entry.original}
                          attacked={entry.attacked}
                          monospace={entry.monospace}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Live signals / reasons */}
            <ReasonsList
              signals={effectiveResult.signals}
              score={effectiveResult.score}
            />

            {/* Next action advice */}
            <AdviceBox
              text={pickActionText(effectiveResult.next_action, lang)}
              verdict={effectiveResult.verdict}
            />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export default function AttackConsolePage() {
  const { queue, isLoading, resetCounter, reportNetworkError } = useAppData();
  const { t, formatMoney } = useT();

  const [selectedBaseId, setSelectedBaseId] = useState<string | null>(null);

  const defaultBaseItem = useMemo(() => {
    if (queue.length === 0) return null;
    return (
      queue.find((item) => item.id === "Q-001") ??
      queue.find((item) => item.result.verdict === "green") ??
      queue[0]
    );
  }, [queue]);

  const baseItem = useMemo(() => {
    if (queue.length === 0) return null;
    if (selectedBaseId) {
      const matched = queue.find((item) => item.id === selectedBaseId);
      if (matched) return matched;
    }
    return defaultBaseItem;
  }, [queue, selectedBaseId, defaultBaseItem]);

  return (
    <div className="space-y-4 sm:space-y-5">
      <div className="ui-page-header sm:items-end">
        <div className="min-w-0">
          <h1 className="ui-page-title">{t.attack.title}</h1>
          <p className="ui-page-subtitle">{t.attack.intro}</p>
        </div>

        {queue.length > 0 && baseItem && (
          <div className="w-full shrink-0 space-y-1 sm:w-80">
            <Label
              htmlFor="attack-base-payment"
              className="ui-label-meta"
            >
              {t.attack.basePaymentLabel}
            </Label>
            <div className="relative">
              <select
                id="attack-base-payment"
                value={baseItem.id}
                onChange={(e) => setSelectedBaseId(e.target.value)}
                className="ui-select h-10 w-full appearance-none sm:h-9"
              >
                {queue.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.id} · {item.request.recipient_name} ·{" "}
                    {formatMoney(item.request.amount_kzt)}
                  </option>
                ))}
              </select>
              <ChevronDown
                aria-hidden="true"
                className="pointer-events-none absolute top-1/2 right-2.5 size-4 -translate-y-1/2 text-muted-foreground"
              />
            </div>
          </div>
        )}
      </div>

      {isLoading && queue.length === 0 ? (
        <div className="space-y-4">
          <div className="ui-panel space-y-4 p-4">
            <div className="flex flex-wrap gap-1.5">
              {Array.from({ length: 5 }).map((_, idx) => (
                <Skeleton key={idx} className="h-8 w-40 rounded-[6px]" />
              ))}
            </div>
            <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2 lg:grid-cols-3">
              {Array.from({ length: 6 }).map((_, idx) => (
                <Skeleton key={idx} className="h-9 w-full rounded-[6px]" />
              ))}
            </div>
          </div>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Skeleton className="h-80 w-full rounded-[8px]" />
            <Skeleton className="h-80 w-full rounded-[8px]" />
          </div>
        </div>
      ) : !baseItem ? (
        <div className="ui-panel">
          <div className="ui-empty">
            <p className="ui-empty-desc">{t.attack.noBasePayments}</p>
            <Link
              href="/"
              className="mt-2 inline-flex min-h-10 items-center gap-1.5 rounded-[6px] border border-input bg-card px-2.5 text-xs font-medium text-foreground transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:min-h-8"
            >
              <ArrowLeft className="size-3.5" />
              <span>{t.attack.goToPayments}</span>
            </Link>
          </div>
        </div>
      ) : (
        <AttackWorkspace
          key={`${baseItem.id}-${resetCounter}`}
          baseItem={baseItem}
          onNetworkError={reportNetworkError}
        />
      )}
    </div>
  );
}
