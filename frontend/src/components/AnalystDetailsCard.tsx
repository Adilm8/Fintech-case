"use client";

import { Lock } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { useT } from "@/i18n";
import {
  formatIntegerForLang,
  localizeBackendText,
  pickReason,
} from "@/lib/format";
import type { AnalystDetails } from "@/lib/types";
import { cn } from "cn";

interface AnalystDetailsCardProps {
  details: AnalystDetails | null | undefined;
  className?: string;
}

export function AnalystDetailsCard({
  details,
  className,
}: AnalystDetailsCardProps) {
  const { t, lang, formatDate, interpolate } = useT();

  const bccAccount = details?.bcc_account ?? null;
  const signalDetails = details?.signal_details ?? [];
  const hasContent = Boolean(bccAccount) || signalDetails.length > 0;

  const signalRulesMap: Record<string, string> = t.signalRules;
  const fieldLabelsMap: Record<string, string> = t.fields;

  return (
    <div
      className={cn(
        "rounded-xl border border-dashed border-slate-300 bg-slate-50/85 p-4 space-y-3 text-slate-800",
        className
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-600">
          <Lock className="size-3.5 shrink-0 text-slate-500" />
          <span>{t.director.analystOnlyTitle}</span>
        </div>
        <Badge
          variant="outline"
          className="h-auto border-slate-300 bg-white/80 px-2 py-0.5 text-[11px] font-medium text-slate-600"
        >
          {t.director.analystConfidentialBadge}
        </Badge>
      </div>

      {!hasContent ? (
        <p className="text-xs text-slate-500">{t.director.analystNoDetails}</p>
      ) : (
        <div className="space-y-3">
          {bccAccount && (
            <div className="grid grid-cols-1 gap-3 rounded-lg border border-slate-200/90 bg-white/75 p-3 text-xs sm:grid-cols-2">
              <div className="min-w-0 space-y-1">
                <div className="text-[11px] font-medium uppercase tracking-wide text-slate-500">
                  {t.director.analystOwnerLabel}
                </div>
                <div className="text-sm font-semibold text-slate-900 break-words">
                  {bccAccount.owner_name}
                </div>
                <div className="flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5 font-mono text-[11px] text-slate-600">
                  <span>
                    {interpolate(t.common.binPrefix, {
                      bin: bccAccount.owner_bin,
                    })}
                  </span>
                  <span aria-hidden="true">·</span>
                  <span className="break-all">{bccAccount.iik}</span>
                </div>
                <div className="pt-0.5">
                  <Badge
                    variant="outline"
                    className={cn(
                      "h-auto px-2 py-0.5 text-[11px] font-medium",
                      bccAccount.owner_matches_recipient
                        ? "border-emerald-200 bg-emerald-50/70 text-emerald-800"
                        : "border-red-200 bg-red-50/80 text-red-800"
                    )}
                  >
                    {bccAccount.owner_matches_recipient
                      ? t.director.analystOwnerMatches
                      : t.director.analystOwnerMismatch}
                  </Badge>
                </div>
              </div>

              <div className="min-w-0 space-y-1">
                <div className="text-[11px] font-medium uppercase tracking-wide text-slate-500">
                  {t.director.analystOpenedLabel}
                </div>
                <div className="text-sm font-semibold tabular-nums text-slate-900">
                  {formatDate(bccAccount.opened_at)}
                </div>
                <div className="text-xs text-slate-600 tabular-nums">
                  {interpolate(t.director.analystAgeDays, {
                    days: formatIntegerForLang(bccAccount.age_days, lang),
                  })}
                </div>
              </div>
            </div>
          )}

          {signalDetails.length > 0 && (
            <div className="space-y-2">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                {t.director.analystSignalDetailsTitle}
              </div>
              <div className="space-y-2">
                {signalDetails.map((detail, idx) => {
                  const ruleTitle =
                    signalRulesMap[detail.rule_id] ?? t.reasons.unknownSignal;
                  const evidenceFieldLabel = detail.evidence
                    ? fieldLabelsMap[detail.evidence.field] ??
                      detail.evidence.field
                    : null;

                  return (
                    <div
                      key={`${detail.rule_id}-${idx}`}
                      className="rounded-lg border border-slate-200/90 bg-white/75 p-2.5 text-xs space-y-1.5"
                    >
                      <div className="font-semibold text-slate-800 break-words">
                        {ruleTitle}
                      </div>
                      <p className="text-xs leading-relaxed text-slate-700 break-words">
                        {pickReason(detail, lang)}
                      </p>
                      {detail.evidence && (
                        <div className="grid grid-cols-1 gap-1 rounded bg-slate-100/80 px-2 py-1.5 font-mono text-[11px] text-slate-600 sm:grid-cols-2">
                          {evidenceFieldLabel && (
                            <div className="min-w-0 break-words">
                              <span className="text-slate-500">
                                {t.reasons.evidenceField}
                              </span>
                              {evidenceFieldLabel}
                            </div>
                          )}
                          {detail.evidence.since && (
                            <div className="min-w-0">
                              <span className="text-slate-500">
                                {t.reasons.evidenceSince}
                              </span>
                              {formatDate(detail.evidence.since)}
                            </div>
                          )}
                          {detail.evidence.expected !== null && (
                            <div className="min-w-0 break-all">
                              <span className="text-slate-500">
                                {t.reasons.evidenceExpected}
                              </span>
                              {localizeBackendText(
                                detail.evidence.expected,
                                lang
                              )}
                            </div>
                          )}
                          {detail.evidence.actual !== null && (
                            <div className="min-w-0 break-all">
                              <span className="text-slate-500">
                                {t.reasons.evidenceActual}
                              </span>
                              {localizeBackendText(
                                detail.evidence.actual,
                                lang
                              )}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
