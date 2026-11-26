"use client";

import Link from "next/link";
import { InfoPageHeader } from "@/components/info/InfoPageHeader";
import { buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useInfoT } from "@/i18n/info";
import { IS_PROD } from "@/lib/mode";
import { cn } from "cn";

export default function AboutPage() {
  const { info } = useInfoT();
  const content = info.about;
  const appHomeHref = IS_PROD ? "/payments" : "/";

  return (
    <div className="space-y-5">
      <InfoPageHeader
        title={content.title}
        subtitle={content.subtitle}
        badge={info.common.prototypeBadge}
        actions={
          <Link
            href={appHomeHref}
            className={cn(
              buttonVariants({ variant: "default" }),
              "min-h-10 sm:min-h-9"
            )}
          >
            {info.common.openQueueCta}
          </Link>
        }
      />

      {/* Problem statement + sourced context */}
      <section aria-labelledby="about-problem-heading">
        <Card>
          <CardHeader className="border-b border-border pb-3">
            <CardTitle>
              <h2 id="about-problem-heading">{content.problemTitle}</h2>
            </CardTitle>
          </CardHeader>

          <CardContent className="space-y-4">
            <p className="max-w-3xl text-sm font-medium leading-6 text-foreground">
              {content.problemLead}
            </p>

            <div className="max-w-3xl space-y-2.5 text-sm leading-6 text-[var(--text-secondary)]">
              {content.problemParagraphs.map((paragraph) => (
                <p key={paragraph}>{paragraph}</p>
              ))}
            </div>

            <div className="ui-kpi-strip-3">
              {content.problemStats.map((stat) => (
                <div key={stat.label} className="ui-kpi-cell">
                  <div className="ui-kpi-value">{stat.value}</div>
                  <div className="space-y-0.5">
                    <div className="text-xs font-medium leading-4 text-foreground">
                      {stat.label}
                    </div>
                    <div className="text-xs leading-4 text-muted-foreground">
                      {stat.source}
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <p className="border-t border-border pt-3 text-xs leading-5 text-muted-foreground">
              {content.statsDisclaimer}
            </p>
          </CardContent>
        </Card>
      </section>

      {/* Solution approach */}
      <section aria-labelledby="about-solution-heading" className="space-y-3">
        <div className="space-y-0.5">
          <h2 id="about-solution-heading" className="ui-section-title">
            {content.solutionTitle}
          </h2>
          <p className="max-w-3xl text-[13px] leading-5 text-muted-foreground">
            {content.solutionSubtitle}
          </p>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {content.solutionCards.map((item) => (
            <div key={item.title} className="ui-panel space-y-1.5 p-4">
              <h3 className="text-sm font-semibold text-foreground">
                {item.title}
              </h3>
              <p className="text-sm leading-5 text-[var(--text-secondary)]">
                {item.description}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* Team (placeholder) */}
      <section aria-labelledby="about-team-heading" className="space-y-3">
        <div className="space-y-0.5">
          <h2 id="about-team-heading" className="ui-section-title">
            {content.teamTitle}
          </h2>
          <p className="max-w-3xl text-[13px] leading-5 text-muted-foreground">
            {content.teamSubtitle}
          </p>
        </div>

        <p className="ui-notice ui-notice-neutral text-xs leading-5 text-[var(--text-secondary)]">
          {content.teamPlaceholderNotice}
        </p>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {content.teamMembers.map((member) => (
            <div
              key={member.role}
              className="ui-panel flex flex-col justify-between gap-2 p-4"
            >
              <div className="space-y-1.5">
                <span className="ui-tag">{member.tag}</span>
                <h3 className="text-sm font-semibold text-foreground">
                  {member.role}
                </h3>
              </div>
              <p className="text-xs leading-5 text-muted-foreground">
                {member.focus}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* Roadmap */}
      <section aria-labelledby="about-roadmap-heading" className="space-y-3">
        <div className="space-y-0.5">
          <h2 id="about-roadmap-heading" className="ui-section-title">
            {content.roadmapTitle}
          </h2>
          <p className="max-w-3xl text-[13px] leading-5 text-muted-foreground">
            {content.roadmapSubtitle}
          </p>
        </div>

        <Card className="py-0">
          <CardContent className="divide-y divide-border p-0">
            {content.roadmap.map((stage, idx) => (
              <div
                key={stage.phase}
                className="flex flex-col gap-2 p-4 sm:flex-row sm:items-start sm:gap-5"
              >
                <div className="flex shrink-0 flex-wrap items-center gap-2 sm:w-44 sm:flex-col sm:items-start sm:gap-1">
                  <span className="ui-tag font-mono">{stage.phase}</span>
                  <span
                    className={cn(
                      "ui-status",
                      idx === 0
                        ? "text-[var(--status-ok-text)]"
                        : "text-muted-foreground"
                    )}
                  >
                    <span
                      aria-hidden="true"
                      className={cn(
                        "ui-status-dot",
                        idx === 0 ? "ui-dot-ok" : "ui-dot-neutral"
                      )}
                    />
                    <span>{stage.statusLabel}</span>
                  </span>
                </div>

                <div className="min-w-0 flex-1 space-y-1">
                  <h3 className="text-sm font-semibold text-foreground">
                    {stage.title}
                  </h3>
                  <CardDescription className="text-sm leading-5">
                    {stage.description}
                  </CardDescription>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
