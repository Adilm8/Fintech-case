"use client";

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
    <div className={cn("ui-panel p-4 space-y-3", className)}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="ui-section-title">{t.director.analystOnlyTitle}</div>
        <span className="ui-tag">{t.director.analystConfidentialBadge}</span>
      </div>

      {!hasContent ? (
        <p className="text-[13px] text-muted-foreground">
          {t.director.analystNoDetails}
        </p>
      ) : (
        <div className="space-y-3">
          {bccAccount && (
            <dl className="ui-dl">
              <div className="ui-dl-row">
                <dt className="ui-dt">{t.director.analystOwnerLabel}</dt>
                <dd className="ui-dd space-y-1">
                  <div className="font-medium text-foreground break-words">
                    {bccAccount.owner_name}
                  </div>
                  <div className="flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5 font-mono text-xs tabular-nums text-muted-foreground">
                    <span>
                      {interpolate(t.common.binPrefix, {
                        bin: bccAccount.owner_bin,
                      })}
                    </span>
                    <span aria-hidden="true">·</span>
                    <span className="break-all">{bccAccount.iik}</span>
                  </div>
                  <div className="pt-0.5">
                    <span
                      className={cn(
                        "ui-status",
                        bccAccount.owner_matches_recipient
                          ? "text-[var(--status-ok-text)]"
                          : "text-[var(--status-danger-text)]"
                      )}
                    >
                      <span
                        aria-hidden="true"
                        className={cn(
                          "ui-status-dot",
                          bccAccount.owner_matches_recipient
                            ? "ui-dot-ok"
                            : "ui-dot-danger"
                        )}
                      />
                      <span>
                        {bccAccount.owner_matches_recipient
                          ? t.director.analystOwnerMatches
                          : t.director.analystOwnerMismatch}
                      </span>
                    </span>
                  </div>
                </dd>
              </div>

              <div className="ui-dl-row">
                <dt className="ui-dt">{t.director.analystOpenedLabel}</dt>
                <dd className="ui-dd flex flex-wrap items-baseline gap-x-2 gap-y-0.5 tabular-nums">
                  <span className="font-medium text-foreground">
                    {formatDate(bccAccount.opened_at)}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {interpolate(t.director.analystAgeDays, {
                      days: formatIntegerForLang(bccAccount.age_days, lang),
                    })}
                  </span>
                </dd>
              </div>
            </dl>
          )}

          {signalDetails.length > 0 && (
            <div className="space-y-2">
              <div className="ui-label-meta">
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
                      className="rounded-[6px] border border-border bg-card p-2.5 text-xs space-y-1.5"
                    >
                      <div className="font-semibold text-foreground break-words">
                        {ruleTitle}
                      </div>
                      <p className="text-[13px] leading-5 text-[var(--text-secondary)] break-words">
                        {pickReason(detail, lang)}
                      </p>
                      {detail.evidence && (
                        <div className="grid grid-cols-1 gap-1 rounded-[4px] bg-muted px-2.5 py-1.5 font-mono text-[11px] tabular-nums text-[var(--text-secondary)] sm:grid-cols-2">
                          {evidenceFieldLabel && (
                            <div className="min-w-0 break-words">
                              <span className="text-muted-foreground">
                                {t.reasons.evidenceField}
                              </span>
                              {evidenceFieldLabel}
                            </div>
                          )}
                          {detail.evidence.since && (
                            <div className="min-w-0">
                              <span className="text-muted-foreground">
                                {t.reasons.evidenceSince}
                              </span>
                              {formatDate(detail.evidence.since)}
                            </div>
                          )}
                          {detail.evidence.expected !== null && (
                            <div className="min-w-0 break-all">
                              <span className="text-muted-foreground">
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
                              <span className="text-muted-foreground">
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
