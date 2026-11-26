"use client";

import Link from "next/link";
import {
  ArrowRight,
  Building2,
  Compass,
  Info,
  Languages,
  Lock,
  Milestone,
  ShieldAlert,
  ShieldCheck,
  Users,
  Zap,
} from "lucide-react";
import { InfoPageHeader } from "@/components/info/InfoPageHeader";
import { Badge } from "@/components/ui/badge";
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

const SOLUTION_ICONS = [Building2, Lock, Zap, Languages] as const;

export default function AboutPage() {
  const { info } = useInfoT();
  const content = info.about;
  const appHomeHref = IS_PROD ? "/payments" : "/";

  return (
    <div className="space-y-6 sm:space-y-8">
      <InfoPageHeader
        icon={Info}
        title={content.title}
        subtitle={content.subtitle}
        badge={info.common.prototypeBadge}
        actions={
          <Link
            href={appHomeHref}
            className={cn(
              buttonVariants({ variant: "default" }),
              "min-h-11 rounded-xl px-4 sm:min-h-9"
            )}
          >
            <span>{info.common.openQueueCta}</span>
            <ArrowRight aria-hidden="true" className="size-4" />
          </Link>
        }
      />

      {/* Problem statement + sourced context */}
      <section aria-labelledby="about-problem-heading">
        <Card>
          <CardHeader className="border-b border-border pb-4">
            <div className="flex items-center gap-2.5">
              <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-red-50 text-red-600">
                <ShieldAlert aria-hidden="true" className="size-4" />
              </div>
              <CardTitle className="text-base sm:text-lg">
                <h2 id="about-problem-heading">{content.problemTitle}</h2>
              </CardTitle>
            </div>
          </CardHeader>

          <CardContent className="space-y-5 pt-5">
            <p className="max-w-3xl text-base font-medium leading-relaxed text-foreground">
              {content.problemLead}
            </p>

            <div className="max-w-3xl space-y-3 text-sm leading-relaxed text-muted-foreground">
              {content.problemParagraphs.map((paragraph) => (
                <p key={paragraph}>{paragraph}</p>
              ))}
            </div>

            <div className="grid grid-cols-1 gap-3 pt-1 sm:grid-cols-3 sm:gap-4">
              {content.problemStats.map((stat) => (
                <div
                  key={stat.label}
                  className="flex flex-col justify-between gap-2 rounded-xl border border-border bg-background/80 p-4"
                >
                  <div className="text-2xl font-bold tracking-tight text-foreground tabular-nums sm:text-3xl">
                    {stat.value}
                  </div>
                  <div className="space-y-1">
                    <div className="text-sm font-medium leading-snug text-foreground">
                      {stat.label}
                    </div>
                    <div className="text-xs leading-relaxed text-muted-foreground">
                      {stat.source}
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <p className="rounded-xl border border-border bg-muted/50 px-3.5 py-2.5 text-xs leading-relaxed text-muted-foreground">
              {content.statsDisclaimer}
            </p>
          </CardContent>
        </Card>
      </section>

      {/* Solution approach */}
      <section aria-labelledby="about-solution-heading" className="space-y-4">
        <div className="space-y-1">
          <h2
            id="about-solution-heading"
            className="text-lg font-semibold tracking-tight text-foreground sm:text-xl"
          >
            {content.solutionTitle}
          </h2>
          <p className="max-w-3xl text-sm text-muted-foreground">
            {content.solutionSubtitle}
          </p>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {content.solutionCards.map((item, idx) => {
            const Icon = SOLUTION_ICONS[idx] ?? ShieldCheck;
            return (
              <Card key={item.title}>
                <CardHeader className="pb-2">
                  <div className="flex items-center gap-2.5">
                    <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-accent text-[var(--brand-text)]">
                      <Icon aria-hidden="true" className="size-4" />
                    </div>
                    <CardTitle className="text-base font-semibold">
                      <h3>{item.title}</h3>
                    </CardTitle>
                  </div>
                </CardHeader>
                <CardContent>
                  <p className="text-sm leading-relaxed text-muted-foreground">
                    {item.description}
                  </p>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </section>

      {/* Team (placeholder) */}
      <section aria-labelledby="about-team-heading" className="space-y-4">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2
              id="about-team-heading"
              className="text-lg font-semibold tracking-tight text-foreground sm:text-xl"
            >
              {content.teamTitle}
            </h2>
          </div>
          <p className="max-w-3xl text-sm text-muted-foreground">
            {content.teamSubtitle}
          </p>
        </div>

        <p className="rounded-xl border border-border bg-card px-4 py-3 text-xs leading-relaxed text-muted-foreground">
          {content.teamPlaceholderNotice}
        </p>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {content.teamMembers.map((member) => (
            <Card key={member.role} className="justify-between">
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-accent text-[var(--brand-text)]">
                    <Users aria-hidden="true" className="size-4" />
                  </div>
                  <Badge
                    variant="secondary"
                    className="h-auto rounded-full px-2.5 py-0.5 text-[11px] font-medium"
                  >
                    {member.tag}
                  </Badge>
                </div>
                <CardTitle className="pt-2 text-sm font-semibold sm:text-base">
                  <h3>{member.role}</h3>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-xs leading-relaxed text-muted-foreground sm:text-sm">
                  {member.focus}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      {/* Roadmap */}
      <section aria-labelledby="about-roadmap-heading" className="space-y-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Compass
              aria-hidden="true"
              className="size-5 text-[var(--brand-text)]"
            />
            <h2
              id="about-roadmap-heading"
              className="text-lg font-semibold tracking-tight text-foreground sm:text-xl"
            >
              {content.roadmapTitle}
            </h2>
          </div>
          <p className="max-w-3xl text-sm text-muted-foreground">
            {content.roadmapSubtitle}
          </p>
        </div>

        <Card>
          <CardContent className="divide-y divide-border p-0">
            {content.roadmap.map((stage, idx) => (
              <div
                key={stage.phase}
                className="flex flex-col gap-3 p-4 sm:flex-row sm:items-start sm:gap-5 sm:p-5"
              >
                <div className="flex shrink-0 items-center gap-2.5 sm:w-44 sm:flex-col sm:items-start sm:gap-1.5">
                  <div className="inline-flex items-center gap-1.5 rounded-xl bg-accent px-2.5 py-1 text-xs font-semibold text-[var(--brand-text)]">
                    <Milestone aria-hidden="true" className="size-3.5" />
                    <span>{stage.phase}</span>
                  </div>
                  <Badge
                    variant="outline"
                    className={cn(
                      "h-auto rounded-full px-2.5 py-0.5 text-[11px] font-medium",
                      idx === 0
                        ? "border-[#00AB75]/35 bg-[#00AB75]/10 text-[#006B49]"
                        : "border-border bg-background text-muted-foreground"
                    )}
                  >
                    {stage.statusLabel}
                  </Badge>
                </div>

                <div className="min-w-0 flex-1 space-y-1">
                  <h3 className="text-sm font-semibold text-foreground sm:text-base">
                    {stage.title}
                  </h3>
                  <CardDescription className="text-sm leading-relaxed">
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
