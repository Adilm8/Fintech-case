"use client";

import { InfoPageHeader } from "@/components/info/InfoPageHeader";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useInfoT } from "@/i18n/info";

export default function SecurityPage() {
  const { info } = useInfoT();
  const content = info.security;

  return (
    <div className="space-y-5">
      <InfoPageHeader
        title={content.title}
        subtitle={content.subtitle}
        badge={info.common.prototypeBadge}
      />

      {/* Key security highlights */}
      <section aria-label={content.title} className="ui-kpi-strip">
        {content.summaryStrip.map((tile) => (
          <div key={tile.label} className="ui-kpi-cell">
            <span className="ui-kpi-label">{tile.label}</span>
            <div className="ui-kpi-value">{tile.value}</div>
            <p className="text-xs leading-4 text-muted-foreground">
              {tile.hint}
            </p>
          </div>
        ))}
      </section>

      {/* Data usage & Transparent rules */}
      <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {content.pillars.map((pillar) => (
          <Card key={pillar.id}>
            <CardHeader className="border-b border-border pb-3">
              <CardTitle>
                <h2>{pillar.title}</h2>
              </CardTitle>
              <CardDescription className="leading-5">
                {pillar.summary}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ul className="list-disc space-y-1.5 pl-4 text-sm leading-5 text-[var(--text-secondary)]">
                {pillar.points.map((point) => (
                  <li key={point}>{point}</li>
                ))}
              </ul>
            </CardContent>
          </Card>
        ))}
      </section>

      {/* Banking secrecy separation */}
      <section aria-labelledby="security-secrecy-heading">
        <Card>
          <CardHeader className="border-b border-border pb-3">
            <CardTitle>
              <h2 id="security-secrecy-heading">
                {content.secrecyComparisonTitle}
              </h2>
            </CardTitle>
            <CardDescription>{content.secrecyComparisonSubtitle}</CardDescription>
          </CardHeader>

          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <div className="ui-notice ui-notice-ok space-y-2">
                <h3 className="text-sm font-semibold text-foreground">
                  {content.clientSeesTitle}
                </h3>
                <ul className="list-disc space-y-1.5 pl-4 text-sm leading-5 text-[var(--text-secondary)]">
                  {content.clientSeesItems.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>

              <div className="ui-notice ui-notice-neutral space-y-2">
                <h3 className="text-sm font-semibold text-foreground">
                  {content.analystSeesTitle}
                </h3>
                <ul className="list-disc space-y-1.5 pl-4 text-sm leading-5 text-[var(--text-secondary)]">
                  {content.analystSeesItems.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            </div>

            <p className="border-t border-border pt-3 text-xs leading-5 text-muted-foreground">
              {content.secrecyDisclaimer}
            </p>
          </CardContent>
        </Card>
      </section>

      {/* Audit log */}
      <section aria-labelledby="security-audit-heading">
        <Card>
          <CardHeader className="border-b border-border pb-3">
            <CardTitle>
              <h2 id="security-audit-heading">{content.auditTitle}</h2>
            </CardTitle>
            <CardDescription>{content.auditSubtitle}</CardDescription>
          </CardHeader>

          <CardContent className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <div className="space-y-2 rounded-[6px] border border-border bg-background p-4">
              <h3 className="text-sm font-semibold text-foreground">
                {content.auditStoredTitle}
              </h3>
              <ul className="list-disc space-y-1.5 pl-4 text-sm leading-5 text-[var(--text-secondary)]">
                {content.auditStoredItems.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>

            <div className="space-y-2 rounded-[6px] border border-border bg-background p-4">
              <h3 className="text-sm font-semibold text-foreground">
                {content.auditNotStoredTitle}
              </h3>
              <ul className="list-disc space-y-1.5 pl-4 text-sm leading-5 text-[var(--text-secondary)]">
                {content.auditNotStoredItems.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          </CardContent>
        </Card>
      </section>

      {/* Invoice recognition warning */}
      <section aria-labelledby="security-invoice-heading">
        <div className="ui-notice ui-notice-warn space-y-2">
          <h2
            id="security-invoice-heading"
            className="text-sm font-semibold text-foreground"
          >
            {content.invoiceNoticeTitle}
          </h2>
          <p className="text-sm leading-5 text-[var(--text-secondary)]">
            {content.invoiceNoticeDescription}
          </p>
          <ul className="list-disc space-y-1 pl-4 text-sm leading-5 text-[var(--text-secondary)]">
            {content.invoiceNoticePoints.map((point) => (
              <li key={point}>{point}</li>
            ))}
          </ul>
        </div>
      </section>

      {/* Honest prototype limitations */}
      <section aria-labelledby="security-limits-heading">
        <Card>
          <CardHeader className="border-b border-border pb-3">
            <CardTitle>
              <h2 id="security-limits-heading">{content.limitationsTitle}</h2>
            </CardTitle>
            <CardDescription>{content.limitationsSubtitle}</CardDescription>
          </CardHeader>

          <CardContent>
            <ul className="list-disc space-y-1.5 pl-4 text-sm leading-5 text-[var(--text-secondary)]">
              {content.limitations.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
