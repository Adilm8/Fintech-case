"use client";

import {
  AlertTriangle,
  CheckCircle2,
  Database,
  Eye,
  EyeOff,
  FileWarning,
  Fingerprint,
  Lock,
  ScrollText,
  ShieldCheck,
  SlidersHorizontal,
} from "lucide-react";
import { InfoPageHeader } from "@/components/info/InfoPageHeader";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useInfoT } from "@/i18n/info";

const SUMMARY_ICONS = [Database, Lock, Fingerprint, FileWarning] as const;
const PILLAR_ICONS = [Database, SlidersHorizontal] as const;

export default function SecurityPage() {
  const { info } = useInfoT();
  const content = info.security;

  return (
    <div className="space-y-6 sm:space-y-8">
      <InfoPageHeader
        icon={ShieldCheck}
        title={content.title}
        subtitle={content.subtitle}
        badge={info.common.prototypeBadge}
      />

      {/* Key security highlights */}
      <section
        aria-label={content.title}
        className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4"
      >
        {content.summaryStrip.map((tile, idx) => {
          const Icon = SUMMARY_ICONS[idx] ?? ShieldCheck;
          return (
            <Card key={tile.label} className="py-4">
              <CardContent className="flex flex-col justify-between gap-2">
                <div className="flex items-start justify-between gap-2">
                  <span className="text-xs font-medium text-muted-foreground sm:text-sm">
                    {tile.label}
                  </span>
                  <div className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-accent text-[var(--brand-text)]">
                    <Icon aria-hidden="true" className="size-4" />
                  </div>
                </div>
                <div className="text-xl font-bold tracking-tight text-foreground sm:text-2xl">
                  {tile.value}
                </div>
                <p className="text-xs leading-relaxed text-muted-foreground">
                  {tile.hint}
                </p>
              </CardContent>
            </Card>
          );
        })}
      </section>

      {/* Data usage & Transparent rules */}
      <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {content.pillars.map((pillar, idx) => {
          const Icon = PILLAR_ICONS[idx] ?? ShieldCheck;
          return (
            <Card key={pillar.id}>
              <CardHeader className="border-b border-border pb-4">
                <div className="flex items-center gap-2.5">
                  <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-accent text-[var(--brand-text)]">
                    <Icon aria-hidden="true" className="size-4" />
                  </div>
                  <CardTitle className="text-base sm:text-lg">
                    <h2>{pillar.title}</h2>
                  </CardTitle>
                </div>
                <CardDescription className="pt-1 leading-relaxed">
                  {pillar.summary}
                </CardDescription>
              </CardHeader>
              <CardContent className="pt-4">
                <ul className="space-y-2.5 text-sm text-foreground/90">
                  {pillar.points.map((point) => (
                    <li key={point} className="flex items-start gap-2.5">
                      <CheckCircle2
                        aria-hidden="true"
                        className="mt-0.5 size-4 shrink-0 text-[var(--brand-text)]"
                      />
                      <span className="leading-relaxed">{point}</span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          );
        })}
      </section>

      {/* Banking secrecy separation */}
      <section aria-labelledby="security-secrecy-heading">
        <Card>
          <CardHeader className="border-b border-border pb-4">
            <div className="flex items-center gap-2.5">
              <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-accent text-[var(--brand-text)]">
                <Lock aria-hidden="true" className="size-4" />
              </div>
              <CardTitle className="text-base sm:text-lg">
                <h2 id="security-secrecy-heading">
                  {content.secrecyComparisonTitle}
                </h2>
              </CardTitle>
            </div>
            <CardDescription className="pt-1">
              {content.secrecyComparisonSubtitle}
            </CardDescription>
          </CardHeader>

          <CardContent className="space-y-4 pt-4">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div className="space-y-3 rounded-xl border border-[#00AB75]/30 bg-[#E8F8F2]/60 p-4">
                <div className="flex items-center gap-2 text-sm font-semibold text-[#064A34]">
                  <EyeOff
                    aria-hidden="true"
                    className="size-4 shrink-0 text-[var(--brand-text)]"
                  />
                  <h3>{content.clientSeesTitle}</h3>
                </div>
                <ul className="space-y-2 text-sm text-[#064A34]/90">
                  {content.clientSeesItems.map((item) => (
                    <li key={item} className="flex items-start gap-2">
                      <span
                        aria-hidden="true"
                        className="mt-2 size-1.5 shrink-0 rounded-full bg-[#00AB75]"
                      />
                      <span className="leading-relaxed">{item}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="space-y-3 rounded-xl border border-border bg-background/80 p-4">
                <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                  <Eye
                    aria-hidden="true"
                    className="size-4 shrink-0 text-muted-foreground"
                  />
                  <h3>{content.analystSeesTitle}</h3>
                </div>
                <ul className="space-y-2 text-sm text-foreground/85">
                  {content.analystSeesItems.map((item) => (
                    <li key={item} className="flex items-start gap-2">
                      <span
                        aria-hidden="true"
                        className="mt-2 size-1.5 shrink-0 rounded-full bg-muted-foreground"
                      />
                      <span className="leading-relaxed">{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            <p className="rounded-xl border border-border bg-muted/50 px-3.5 py-2.5 text-xs leading-relaxed text-muted-foreground">
              {content.secrecyDisclaimer}
            </p>
          </CardContent>
        </Card>
      </section>

      {/* Audit log */}
      <section aria-labelledby="security-audit-heading">
        <Card>
          <CardHeader className="border-b border-border pb-4">
            <div className="flex items-center gap-2.5">
              <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-accent text-[var(--brand-text)]">
                <ScrollText aria-hidden="true" className="size-4" />
              </div>
              <CardTitle className="text-base sm:text-lg">
                <h2 id="security-audit-heading">{content.auditTitle}</h2>
              </CardTitle>
            </div>
            <CardDescription className="pt-1">
              {content.auditSubtitle}
            </CardDescription>
          </CardHeader>

          <CardContent className="grid grid-cols-1 gap-4 pt-4 md:grid-cols-2">
            <div className="space-y-2.5 rounded-xl border border-border bg-background/70 p-4">
              <h3 className="text-sm font-semibold text-foreground">
                {content.auditStoredTitle}
              </h3>
              <ul className="space-y-2 text-sm text-foreground/90">
                {content.auditStoredItems.map((item) => (
                  <li key={item} className="flex items-start gap-2.5">
                    <CheckCircle2
                      aria-hidden="true"
                      className="mt-0.5 size-4 shrink-0 text-[var(--brand-text)]"
                    />
                    <span className="leading-relaxed">{item}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="space-y-2.5 rounded-xl border border-border bg-background/70 p-4">
              <h3 className="text-sm font-semibold text-foreground">
                {content.auditNotStoredTitle}
              </h3>
              <ul className="space-y-2 text-sm text-foreground/90">
                {content.auditNotStoredItems.map((item) => (
                  <li key={item} className="flex items-start gap-2.5">
                    <EyeOff
                      aria-hidden="true"
                      className="mt-0.5 size-4 shrink-0 text-muted-foreground"
                    />
                    <span className="leading-relaxed">{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          </CardContent>
        </Card>
      </section>

      {/* Invoice recognition warning */}
      <section aria-labelledby="security-invoice-heading">
        <Alert className="rounded-2xl border-amber-300/90 bg-amber-50/85 px-4 py-4 text-amber-950 sm:px-5">
          <FileWarning aria-hidden="true" className="size-4 text-amber-700" />
          <AlertTitle className="text-base font-semibold text-amber-950">
            <h2 id="security-invoice-heading">{content.invoiceNoticeTitle}</h2>
          </AlertTitle>
          <AlertDescription className="mt-1 space-y-2.5 text-amber-950/90">
            <p className="leading-relaxed">{content.invoiceNoticeDescription}</p>
            <ul className="space-y-1.5 text-sm">
              {content.invoiceNoticePoints.map((point) => (
                <li key={point} className="flex items-start gap-2">
                  <span
                    aria-hidden="true"
                    className="mt-2 size-1.5 shrink-0 rounded-full bg-amber-700"
                  />
                  <span className="leading-relaxed">{point}</span>
                </li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      </section>

      {/* Honest prototype limitations */}
      <section aria-labelledby="security-limits-heading">
        <Card>
          <CardHeader className="border-b border-border pb-4">
            <div className="flex items-center gap-2.5">
              <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-muted text-foreground/75">
                <AlertTriangle aria-hidden="true" className="size-4" />
              </div>
              <CardTitle className="text-base sm:text-lg">
                <h2 id="security-limits-heading">{content.limitationsTitle}</h2>
              </CardTitle>
            </div>
            <CardDescription className="pt-1">
              {content.limitationsSubtitle}
            </CardDescription>
          </CardHeader>

          <CardContent className="pt-4">
            <ul className="space-y-2 text-sm text-foreground/90">
              {content.limitations.map((item) => (
                <li key={item} className="flex items-start gap-2.5">
                  <span
                    aria-hidden="true"
                    className="mt-2 size-1.5 shrink-0 rounded-full bg-muted-foreground"
                  />
                  <span className="leading-relaxed">{item}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
