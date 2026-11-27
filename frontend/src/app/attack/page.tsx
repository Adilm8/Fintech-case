"use client";

import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  ArrowRight,
  ChevronDown,
  Loader2,
  SlidersHorizontal,
} from "lucide-react";
import { AdviceBox } from "@/components/AdviceBox";
import { useAppData } from "@/components/AppShell";
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
import { CompactReasonsList } from "./CompactReasonsList";

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

type PresetId =
  | "homoglyph"
  | "invisible"
  | "other_bank"
  | "own_bin"
  | "bcc_other"
  | "amount_4x"
  | "urgent"
  | "combined_new_requisites";

const DEFAULT_KBE = "17";
const DEFAULT_KNP = "710";
const COMBINED_URGENT_PHRASE = "срочно, новые реквизиты";
const COMBINED_AMOUNT_MULTIPLIER = 3.6;

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

function cloneBaseRequest(req: CheckRequest): CheckRequest {
  const cleanKbe = req.kbe?.replace(/\D+/g, "").slice(0, 2);
  const cleanKnp = req.knp?.replace(/\D+/g, "").slice(0, 3);
  return {
    ...(req.payer_id !== undefined ? { payer_id: req.payer_id } : {}),
    recipient_name: req.recipient_name,
    recipient_bin: req.recipient_bin,
    recipient_iik: req.recipient_iik,
    recipient_bik: req.recipient_bik,
    amount_kzt: req.amount_kzt,
    purpose: req.purpose,
    ...(cleanKbe ? { kbe: cleanKbe } : {}),
    ...(cleanKnp ? { knp: cleanKnp } : {}),
  };
}

function applyCombinedNewRequisitesAttack(request: CheckRequest): CheckRequest {
  const withHomoglyph = applyHomoglyphAttack(request);
  const withNewIik = applyOtherBankIikAttack(withHomoglyph);
  const withInflatedAmount = applyMultiplyAmountAttack(
    withNewIik,
    COMBINED_AMOUNT_MULTIPLIER
  );
  const trimmedPurpose = withInflatedAmount.purpose.trim();
  const lowerPurpose = trimmedPurpose.toLowerCase();
  const nextPurpose = lowerPurpose.includes(COMBINED_URGENT_PHRASE)
    ? trimmedPurpose
    : trimmedPurpose
      ? `${trimmedPurpose}, ${COMBINED_URGENT_PHRASE}`
      : COMBINED_URGENT_PHRASE;

  return {
    ...withInflatedAmount,
    purpose: nextPurpose,
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
  compact = false,
}: {
  original: string;
  attacked: string;
  monospace?: boolean;
  compact?: boolean;
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
          ? compact
            ? "font-mono text-xs leading-4 tabular-nums break-all [overflow-wrap:anywhere]"
            : "font-mono text-xs tabular-nums sm:text-sm break-all [overflow-wrap:anywhere]"
          : compact
            ? "text-xs leading-4 break-words [overflow-wrap:anywhere]"
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
                  <span className="font-mono text-[10px] leading-none">
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
  const [activePresetId, setActivePresetId] = useState<PresetId | null>(null);
  const [manualOpen, setManualOpen] = useState(false);
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

  const applyPresetFromBase = (
    presetId: PresetId,
    fn: (req: CheckRequest) => CheckRequest
  ) => {
    const cleanBase = cloneBaseRequest(baseItem.request);
    const nextReq = fn(cleanBase);
    setAttackedForm(requestToForm(nextReq));
    setActivePresetId(presetId);
    setCheckError(null);
  };

  const handleHomoglyphClick = () => {
    const cleanBase = cloneBaseRequest(baseItem.request);
    const nextReq = applyHomoglyphAttack(cleanBase);
    if (nextReq.recipient_name === cleanBase.recipient_name) {
      notify.info(t.attack.btnHomoglyph, t.attack.noHomoglyphLeft);
      return;
    }
    setAttackedForm(requestToForm(nextReq));
    setActivePresetId("homoglyph");
    setCheckError(null);
  };

  const handleInvisibleCharClick = () => {
    const cleanBase = cloneBaseRequest(baseItem.request);
    const nextReq = applyInvisibleCharAttack(cleanBase);
    if (nextReq.recipient_name === cleanBase.recipient_name) {
      notify.info(
        t.attack.btnInvisibleChar,
        t.attack.invisibleCharAlreadyPresent
      );
      return;
    }
    setAttackedForm(requestToForm(nextReq));
    setActivePresetId("invisible");
    setCheckError(null);
  };

  const handleReset = () => {
    requestSeqRef.current += 1;
    setAttackedForm(originalForm);
    setActivePresetId(null);
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
    setActivePresetId(null);
    if (checkError) setCheckError(null);
  };

  const presets: {
    id: PresetId;
    label: string;
    hint: string;
    featured?: boolean;
    onClick: () => void;
  }[] = [
    {
      id: "homoglyph",
      label: t.attack.btnHomoglyph,
      hint: t.attack.hintHomoglyph,
      onClick: handleHomoglyphClick,
    },
    {
      id: "invisible",
      label: t.attack.btnInvisibleChar,
      hint: t.attack.hintInvisibleChar,
      onClick: handleInvisibleCharClick,
    },
    {
      id: "other_bank",
      label: t.attack.btnOtherBank,
      hint: t.attack.hintOtherBank,
      onClick: () => applyPresetFromBase("other_bank", applyOtherBankIikAttack),
    },
    {
      id: "own_bin",
      label: t.attack.btnOwnBinOwnAccount,
      hint: t.attack.hintOwnBinOwnAccount,
      onClick: () => applyPresetFromBase("own_bin", applyOwnBinOwnAccountAttack),
    },
    {
      id: "bcc_other",
      label: t.attack.btnBccOtherCompany,
      hint: t.attack.hintBccOtherCompany,
      onClick: () => applyPresetFromBase("bcc_other", applyBccOtherCompanyAttack),
    },
    {
      id: "amount_4x",
      label: t.attack.btnAmount4x,
      hint: t.attack.hintAmount4x,
      onClick: () =>
        applyPresetFromBase("amount_4x", (req) =>
          applyMultiplyAmountAttack(req, 4)
        ),
    },
    {
      id: "urgent",
      label: t.attack.btnAddUrgent,
      hint: t.attack.hintAddUrgent,
      onClick: () => applyPresetFromBase("urgent", applyUrgentPurposeAttack),
    },
    {
      id: "combined_new_requisites",
      label: t.attack.btnCombinedNewRequisites,
      hint: t.attack.hintCombinedNewRequisites,
      featured: true,
      onClick: () =>
        applyPresetFromBase(
          "combined_new_requisites",
          applyCombinedNewRequisitesAttack
        ),
    },
  ];

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

  const transitionNoticeClass = !isDirty
    ? "ui-notice-neutral"
    : attackedVerdict === "red"
      ? "ui-notice-danger"
      : attackedVerdict === "invalid"
        ? "ui-notice-invalid"
        : attackedVerdict === "yellow"
          ? "ui-notice-warn"
          : attackedVerdict === "green"
            ? "ui-notice-ok"
            : "ui-notice-neutral";

  const attackedChipToneClass =
    isDirty && (attackedVerdict === "red" || attackedVerdict === "invalid")
      ? "border-[#FCA5A5] bg-[#FEF2F2]"
      : isDirty && attackedVerdict === "yellow"
        ? "border-[#FCD34D] bg-[#FFFBEB]"
        : isDirty && attackedVerdict === "green"
          ? "border-[#00AB75]/40 bg-[#F0FAF6]"
          : "border-border bg-muted/50";

  return (
    <div className="space-y-2.5">
      {/* 1. Quick Attacks */}
      <Card size="sm" className="min-w-0 gap-0 py-0">
        <CardHeader className="border-b border-border px-3 py-2 [.border-b]:pb-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex min-w-0 flex-wrap items-baseline gap-x-2.5 gap-y-0.5">
              <CardTitle className="text-sm leading-5">
                {t.attack.quickAttacksTitle}
              </CardTitle>
              <span className="hidden text-xs text-muted-foreground md:inline">
                {t.attack.editableFieldsHint}
              </span>
            </div>
            <Button
              type="button"
              variant="outline"
              size="xs"
              onClick={handleReset}
              disabled={!isDirty}
              className="h-7 px-2.5 text-xs"
            >
              {t.attack.btnReset}
            </Button>
          </div>
        </CardHeader>

        <CardContent className="px-3 py-2.5">
          <div className="grid grid-cols-1 gap-x-2 gap-y-2 sm:grid-cols-2 lg:grid-cols-4">
            {presets.map((preset) => {
              const isActive = activePresetId === preset.id;
              return (
                <div key={preset.id} className="flex min-w-0 flex-col gap-0.5">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    aria-pressed={isActive}
                    onClick={preset.onClick}
                    className={cn(
                      "h-auto min-h-7 w-full justify-start px-2.5 py-1 text-left text-xs font-medium leading-[1.2] whitespace-normal",
                      isActive
                        ? "border-[#00AB75] bg-[#F0FAF6] text-[#007A53] ring-1 ring-[#00AB75]/25 hover:bg-[#F0FAF6] hover:text-[#007A53]"
                        : preset.featured
                          ? "border-[#00AB75]/45 bg-[#F0FAF6]/55 text-foreground hover:bg-[#F0FAF6]"
                          : ""
                    )}
                  >
                    {preset.label}
                  </Button>
                  <span
                    title={preset.hint}
                    className="block truncate px-0.5 text-[11px] leading-[1.25] text-muted-foreground"
                  >
                    {preset.hint}
                  </span>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* 2. Verdict transition strip (immediately below Quick Attacks) */}
      <div
        role="status"
        className={cn(
          "ui-notice flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5 px-3 py-2",
          transitionNoticeClass
        )}
      >
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold text-foreground">
            {verdictChanged
              ? t.attack.verdictChangedTitle
              : t.attack.verdictTransitionTitle}
            :
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-[5px] border border-border bg-muted/50 px-2 py-0.5">
            <VerdictBadge verdict={originalVerdict} />
            <span className="font-mono text-xs font-semibold tabular-nums text-foreground">
              {baseItem.result.score}/100
            </span>
          </span>
          <ArrowRight
            className="size-3.5 shrink-0 text-muted-foreground"
            aria-hidden="true"
          />
          <span
            className={cn(
              "inline-flex items-center gap-1.5 rounded-[5px] border px-2 py-0.5",
              attackedChipToneClass
            )}
          >
            <VerdictBadge verdict={attackedVerdict} />
            <span className="font-mono text-xs font-semibold tabular-nums text-foreground">
              {effectiveResult.score}/100
            </span>
          </span>
        </div>

        <div className="flex items-center gap-2 text-xs">
          {isChecking ? (
            <span className="inline-flex items-center gap-1 text-muted-foreground">
              <Loader2 className="size-3 animate-spin" aria-hidden="true" />
              <span>{t.attack.checkingLive}</span>
            </span>
          ) : !isDirty ? (
            <span className="text-muted-foreground">
              {t.attack.verdictUnchangedHint}
            </span>
          ) : (
            <span className="font-mono font-semibold tabular-nums text-foreground">
              {baseItem.result.score} → {effectiveResult.score} / 100
            </span>
          )}
        </div>
      </div>

      {/* 3. Side-by-side comparison cards: Original / After Attack */}
      <div className="grid grid-cols-1 items-start gap-2.5 lg:grid-cols-2">
        {/* Left Card: Original */}
        <Card size="sm" className="min-w-0 gap-0 py-0">
          <CardHeader className="gap-0.5 border-b border-border px-3 py-2 [.border-b]:pb-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <CardTitle className="text-sm leading-5">
                {t.attack.originalCardTitle}
              </CardTitle>
              <div className="flex items-center gap-2">
                <VerdictBadge verdict={baseItem.result.verdict} />
                <span className="font-mono text-[11px] font-medium text-muted-foreground tabular-nums">
                  {interpolate(t.attack.scoreLabel, {
                    score: baseItem.result.score,
                  })}
                </span>
              </div>
            </div>
            <CardDescription className="truncate text-xs leading-4">
              {pickHeadline(baseItem.result, lang)}
            </CardDescription>
          </CardHeader>

          <CardContent className="px-3 py-1.5">
            <dl className="divide-y divide-border/70 text-xs">
              <div className="grid grid-cols-1 gap-0.5 py-1.5 sm:grid-cols-[9rem_minmax(0,1fr)] sm:items-baseline sm:gap-2">
                <dt className="text-[11px] font-medium text-muted-foreground">
                  {t.fields.name}
                </dt>
                <dd className="min-w-0 font-medium text-foreground break-words">
                  {baseItem.request.recipient_name}
                </dd>
              </div>
              <div className="grid grid-cols-1 gap-0.5 py-1.5 sm:grid-cols-[9rem_minmax(0,1fr)] sm:items-baseline sm:gap-2">
                <dt className="text-[11px] font-medium text-muted-foreground">
                  {t.fields.bin}
                </dt>
                <dd className="min-w-0 font-mono tabular-nums text-foreground">
                  {baseItem.request.recipient_bin}
                </dd>
              </div>
              <div className="grid grid-cols-1 gap-0.5 py-1.5 sm:grid-cols-[9rem_minmax(0,1fr)] sm:items-baseline sm:gap-2">
                <dt className="text-[11px] font-medium text-muted-foreground">
                  {t.fields.iik}
                </dt>
                <dd className="min-w-0 font-mono tabular-nums text-foreground break-all">
                  {baseItem.request.recipient_iik}
                </dd>
              </div>
              <div className="grid grid-cols-1 gap-0.5 py-1.5 sm:grid-cols-[9rem_minmax(0,1fr)] sm:items-baseline sm:gap-2">
                <dt className="text-[11px] font-medium text-muted-foreground">
                  {t.fields.bik}
                </dt>
                <dd className="min-w-0 font-mono tabular-nums text-foreground">
                  {baseItem.request.recipient_bik}
                </dd>
              </div>
              <div className="grid grid-cols-1 gap-0.5 py-1.5 sm:grid-cols-[9rem_minmax(0,1fr)] sm:items-baseline sm:gap-2">
                <dt className="text-[11px] font-medium text-muted-foreground">
                  {t.fields.amount}
                </dt>
                <dd className="min-w-0 font-medium tabular-nums text-foreground whitespace-nowrap">
                  {formatMoney(baseItem.request.amount_kzt)}
                </dd>
              </div>
              <div className="grid grid-cols-2 gap-3 py-1.5">
                <div className="flex min-w-0 items-baseline justify-between gap-2 sm:grid sm:grid-cols-[9rem_minmax(0,1fr)] sm:gap-2">
                  <dt className="text-[11px] font-medium text-muted-foreground">
                    {t.attack.kbeLabel}
                  </dt>
                  <dd className="min-w-0 font-mono tabular-nums text-foreground">
                    {originalForm.kbe || "—"}
                  </dd>
                </div>
                <div className="flex min-w-0 items-baseline justify-between gap-2 sm:justify-start sm:gap-3">
                  <dt className="text-[11px] font-medium text-muted-foreground">
                    {t.attack.knpLabel}
                  </dt>
                  <dd className="min-w-0 font-mono tabular-nums text-foreground">
                    {originalForm.knp || "—"}
                  </dd>
                </div>
              </div>
              <div className="grid grid-cols-1 gap-0.5 py-1.5 sm:grid-cols-[9rem_minmax(0,1fr)] sm:items-baseline sm:gap-2">
                <dt className="text-[11px] font-medium text-muted-foreground">
                  {t.attack.purposeLabel}
                </dt>
                <dd className="min-w-0 leading-4 text-foreground break-words">
                  {baseItem.request.purpose}
                </dd>
              </div>
            </dl>
          </CardContent>
        </Card>

        {/* Right Card: After Attack (live) */}
        <Card
          size="sm"
          className={cn(
            "min-w-0 gap-0 py-0 transition-opacity",
            isChecking && "opacity-85"
          )}
        >
          <CardHeader className="gap-0.5 border-b border-border px-3 py-2 [.border-b]:pb-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <CardTitle className="text-sm leading-5">
                  {t.attack.attackedCardTitle}
                </CardTitle>
                <span
                  aria-live="polite"
                  className={cn(
                    "inline-flex items-center gap-1 text-[11px] text-muted-foreground transition-opacity",
                    isChecking
                      ? "opacity-100"
                      : "pointer-events-none opacity-0"
                  )}
                >
                  <Loader2 className="size-3 animate-spin" aria-hidden="true" />
                  <span>{t.attack.checkingLive}</span>
                </span>
              </div>
              <div className="flex items-center gap-2">
                <VerdictBadge verdict={effectiveResult.verdict} />
                <span className="shrink-0 font-mono text-[11px] font-medium text-foreground tabular-nums">
                  {interpolate(t.attack.scoreLabel, {
                    score: effectiveResult.score,
                  })}
                </span>
              </div>
            </div>

            <CardDescription className="text-xs font-medium leading-4 text-foreground break-words">
              {pickHeadline(effectiveResult, lang)}
            </CardDescription>
          </CardHeader>

          <CardContent className="space-y-2 px-3 py-2.5">
            {checkError && (
              <div
                role="alert"
                className="ui-notice ui-notice-danger space-y-0.5 px-2.5 py-1.5"
              >
                <div className="text-xs font-semibold text-[var(--status-danger-text)]">
                  {t.attack.checkErrorTitle}
                </div>
                <p className="text-xs text-foreground break-words">
                  {checkError}
                </p>
              </div>
            )}

            {/* Highlighted character diffs */}
            <div className="ui-subpanel space-y-1 px-2.5 py-2">
              <div className="text-[11px] font-medium leading-4 text-muted-foreground">
                {t.attack.diffPreviewTitle}
              </div>
              {changedFields.length === 0 ? (
                <p className="text-xs leading-4 text-muted-foreground">
                  {t.attack.noFieldChanges}
                </p>
              ) : (
                <div className="space-y-1">
                  {changedFields.map((entry) => (
                    <div
                      key={entry.key}
                      className="grid grid-cols-1 gap-x-2 gap-y-0.5 sm:grid-cols-[8rem_minmax(0,1fr)] sm:items-baseline"
                    >
                      <div className="text-[11px] font-medium leading-4 text-muted-foreground">
                        {entry.label}
                      </div>
                      <div className="min-w-0">
                        <CharDiffHighlight
                          original={entry.original}
                          attacked={entry.attacked}
                          monospace={entry.monospace}
                          compact
                        />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Live signals / reasons */}
            <CompactReasonsList
              signals={effectiveResult.signals}
              score={effectiveResult.score}
            />

            {/* Next action advice */}
            <AdviceBox
              text={pickActionText(effectiveResult.next_action, lang)}
              verdict={effectiveResult.verdict}
              className="space-y-0.5 px-2.5 py-1.5 [&_p]:text-xs [&_p]:leading-4"
            />
          </CardContent>
        </Card>
      </div>

      {/* 4. Collapsible manual 8-field form (closed by default) */}
      <Card size="sm" className="min-w-0 gap-0 py-0">
        <button
          type="button"
          onClick={() => setManualOpen((prev) => !prev)}
          aria-expanded={manualOpen}
          aria-controls="attack-manual-fields"
          className={cn(
            "flex w-full items-center justify-between gap-2 px-3 py-2 text-left transition-colors hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40",
            manualOpen && "border-b border-border"
          )}
        >
          <span className="flex min-w-0 items-center gap-2">
            <SlidersHorizontal
              className="size-3.5 shrink-0 text-muted-foreground"
              aria-hidden="true"
            />
            <span className="text-xs font-semibold text-foreground">
              {t.attack.manualFieldsTitle}
            </span>
            {changedFields.length > 0 && (
              <span className="ui-tag">
                {interpolate(t.attack.manualFieldsCount, {
                  count: changedFields.length,
                })}
              </span>
            )}
          </span>
          <span className="flex shrink-0 items-center gap-2 text-xs text-muted-foreground">
            <ChevronDown
              aria-hidden="true"
              className={cn(
                "size-4 transition-transform duration-150",
                manualOpen && "rotate-180"
              )}
            />
          </span>
        </button>

        {!manualOpen && isDirty && !parsedPayload && (
          <div className="border-t border-border px-3 py-2">
            <div
              role="status"
              className="ui-notice ui-notice-warn py-1.5 text-xs text-foreground"
            >
              {t.attack.incompleteHint}
            </div>
          </div>
        )}

        {manualOpen && (
          <CardContent
            id="attack-manual-fields"
            className="space-y-3 px-3 py-3"
          >
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <div className="min-w-0 space-y-1 sm:col-span-2 lg:col-span-2">
                <div className="flex items-center justify-between gap-2">
                  <Label
                    htmlFor="attack_recipient_name"
                    className="text-xs"
                  >
                    {t.queue.labelRecipientName}
                  </Label>
                  {attackedForm.recipient_name !==
                    originalForm.recipient_name && (
                    <span className="text-[11px] text-muted-foreground">
                      {t.attack.modifiedBadge}
                    </span>
                  )}
                </div>
                <Input
                  id="attack_recipient_name"
                  value={attackedForm.recipient_name}
                  onChange={(e) =>
                    updateField("recipient_name", e.target.value)
                  }
                  className="h-9 bg-card text-sm sm:h-8"
                />
                {attackedForm.recipient_name !==
                  originalForm.recipient_name && (
                  <div className="rounded-[6px] border border-border bg-muted/40 px-2.5 py-1">
                    <CharDiffHighlight
                      original={originalForm.recipient_name}
                      attacked={attackedForm.recipient_name}
                      compact
                    />
                  </div>
                )}
              </div>

              <div className="min-w-0 space-y-1">
                <div className="flex items-center justify-between gap-2">
                  <Label htmlFor="attack_amount_kzt" className="text-xs">
                    {t.queue.labelAmount}
                  </Label>
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
                  className="h-9 bg-card text-sm tabular-nums sm:h-8"
                />
              </div>

              <div className="min-w-0 space-y-1">
                <div className="flex items-center justify-between gap-2">
                  <Label htmlFor="attack_recipient_bin" className="text-xs">
                    {t.queue.labelBin}
                  </Label>
                  {attackedForm.recipient_bin !==
                    originalForm.recipient_bin && (
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
                  className="h-9 bg-card font-mono text-sm tabular-nums sm:h-8"
                />
                {attackedForm.recipient_bin !== originalForm.recipient_bin && (
                  <div className="rounded-[6px] border border-border bg-muted/40 px-2.5 py-1">
                    <CharDiffHighlight
                      original={originalForm.recipient_bin}
                      attacked={attackedForm.recipient_bin}
                      monospace
                      compact
                    />
                  </div>
                )}
              </div>

              <div className="min-w-0 space-y-1">
                <div className="flex items-center justify-between gap-2">
                  <Label htmlFor="attack_recipient_iik" className="text-xs">
                    {t.queue.labelIik}
                  </Label>
                  {attackedForm.recipient_iik !==
                    originalForm.recipient_iik && (
                    <span className="text-[11px] text-muted-foreground">
                      {t.attack.modifiedBadge}
                    </span>
                  )}
                </div>
                <Input
                  id="attack_recipient_iik"
                  value={attackedForm.recipient_iik}
                  onChange={(e) => updateField("recipient_iik", e.target.value)}
                  className="h-9 bg-card font-mono text-sm uppercase tabular-nums sm:h-8"
                />
                {attackedForm.recipient_iik !== originalForm.recipient_iik && (
                  <div className="rounded-[6px] border border-border bg-muted/40 px-2.5 py-1">
                    <CharDiffHighlight
                      original={originalForm.recipient_iik}
                      attacked={attackedForm.recipient_iik}
                      monospace
                      compact
                    />
                  </div>
                )}
              </div>

              <div className="min-w-0 space-y-1">
                <div className="flex items-center justify-between gap-2">
                  <Label htmlFor="attack_recipient_bik" className="text-xs">
                    {t.queue.labelBik}
                  </Label>
                  {attackedForm.recipient_bik !==
                    originalForm.recipient_bik && (
                    <span className="text-[11px] text-muted-foreground">
                      {t.attack.modifiedBadge}
                    </span>
                  )}
                </div>
                <Input
                  id="attack_recipient_bik"
                  value={attackedForm.recipient_bik}
                  onChange={(e) => updateField("recipient_bik", e.target.value)}
                  className="h-9 bg-card font-mono text-sm uppercase tabular-nums sm:h-8"
                />
                {attackedForm.recipient_bik !== originalForm.recipient_bik && (
                  <div className="rounded-[6px] border border-border bg-muted/40 px-2.5 py-1">
                    <CharDiffHighlight
                      original={originalForm.recipient_bik}
                      attacked={attackedForm.recipient_bik}
                      monospace
                      compact
                    />
                  </div>
                )}
              </div>

              <div className="min-w-0 space-y-1">
                <div className="flex items-center justify-between gap-2">
                  <Label htmlFor="attack_kbe" className="text-xs">
                    {t.queue.labelKbe}
                  </Label>
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
                  className="h-9 bg-card font-mono text-sm tabular-nums sm:h-8"
                />
              </div>

              <div className="min-w-0 space-y-1">
                <div className="flex items-center justify-between gap-2">
                  <Label htmlFor="attack_knp" className="text-xs">
                    {t.queue.labelKnp}
                  </Label>
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
                  className="h-9 bg-card font-mono text-sm tabular-nums sm:h-8"
                />
              </div>

              <div className="min-w-0 space-y-1 sm:col-span-2 lg:col-span-3">
                <div className="flex items-center justify-between gap-2">
                  <Label htmlFor="attack_purpose" className="text-xs">
                    {t.queue.labelPurpose}
                  </Label>
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
                  className="h-9 bg-card text-sm sm:h-8"
                />
                {attackedForm.purpose !== originalForm.purpose && (
                  <div className="rounded-[6px] border border-border bg-muted/40 px-2.5 py-1">
                    <CharDiffHighlight
                      original={originalForm.purpose}
                      attacked={attackedForm.purpose}
                      compact
                    />
                  </div>
                )}
              </div>
            </div>

            {isDirty && !parsedPayload && (
              <div
                role="status"
                className="ui-notice ui-notice-warn py-1.5 text-xs text-foreground"
              >
                {t.attack.incompleteHint}
              </div>
            )}
          </CardContent>
        )}
      </Card>
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
    <div className="space-y-2.5">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-lg font-semibold leading-tight tracking-[-0.015em] text-foreground">
            {t.attack.title}
          </h1>
          <p className="mt-0.5 text-xs leading-4 text-muted-foreground">
            {t.attack.intro}
          </p>
        </div>

        {queue.length > 0 && baseItem && (
          <div className="flex w-full shrink-0 flex-col gap-1 sm:w-auto sm:flex-row sm:items-center sm:gap-2">
            <Label
              htmlFor="attack-base-payment"
              className="ui-label-meta shrink-0 whitespace-nowrap"
            >
              {t.attack.basePaymentLabel}
            </Label>
            <div className="relative w-full sm:w-72">
              <select
                id="attack-base-payment"
                value={baseItem.id}
                onChange={(e) => setSelectedBaseId(e.target.value)}
                className="ui-select h-9 w-full appearance-none text-xs sm:h-8 sm:text-xs"
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
                className="pointer-events-none absolute top-1/2 right-2.5 size-3.5 -translate-y-1/2 text-muted-foreground"
              />
            </div>
          </div>
        )}
      </div>

      {isLoading && queue.length === 0 ? (
        <div className="space-y-2.5">
          <div className="ui-panel space-y-2.5 p-3">
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
              {Array.from({ length: 8 }).map((_, idx) => (
                <div key={idx} className="space-y-1">
                  <Skeleton className="h-7 w-full rounded-[6px]" />
                  <Skeleton className="h-3 w-4/5 rounded-[4px]" />
                </div>
              ))}
            </div>
          </div>
          <Skeleton className="h-10 w-full rounded-[6px]" />
          <div className="grid grid-cols-1 gap-2.5 lg:grid-cols-2">
            <Skeleton className="h-64 w-full rounded-[8px]" />
            <Skeleton className="h-64 w-full rounded-[8px]" />
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
