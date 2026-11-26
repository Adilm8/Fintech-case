"use client";

import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  Building2,
  CheckCircle2,
  FileCheck2,
  FileUp,
  History,
  Languages,
  ScanSearch,
  ShieldCheck,
  TrendingUp,
  UserCheck,
} from "lucide-react";
import { InfoPageHeader } from "@/components/info/InfoPageHeader";
import { VerificationFlowDiagram } from "@/components/info/VerificationFlowDiagram";
import { VerdictBadge } from "@/components/VerdictBadge";
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
import { VERDICT_STYLES } from "@/lib/format";
import { IS_PROD } from "@/lib/mode";
import { cn } from "cn";

const STEP_ICONS = [
  FileCheck2,
  History,
  Building2,
  ScanSearch,
  TrendingUp,
] as const;

const WORKFLOW_ICONS = [FileUp, UserCheck, Languages] as const;

export default function HowItWorksPage() {
  const { info } = useInfoT();
  const content = info.howItWorks;
  const appHomeHref = IS_PROD ? "/payments" : "/";

  return (
    <div className="space-y-6 sm:space-y-8">
      <InfoPageHeader
        icon={BookOpen}
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

      {/* Architecture / Flow Diagram */}
      <section aria-labelledby="how-diagram-heading">
        <Card>
          <CardHeader className="border-b border-border pb-4">
            <CardTitle className="text-base sm:text-lg">
              <h2 id="how-diagram-heading">{content.diagramTitle}</h2>
            </CardTitle>
            <CardDescription>{content.diagramSubtitle}</CardDescription>
          </CardHeader>
          <CardContent className="pt-4">
            <VerificationFlowDiagram />
          </CardContent>
        </Card>
      </section>

      {/* Step-by-step checks */}
      <section aria-labelledby="how-steps-heading" className="space-y-4">
        <div className="space-y-1">
          <h2
            id="how-steps-heading"
            className="text-lg font-semibold tracking-tight text-foreground sm:text-xl"
          >
            {content.stepsTitle}
          </h2>
          <p className="max-w-3xl text-sm text-muted-foreground">
            {content.stepsSubtitle}
          </p>
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {content.steps.map((step, idx) => {
            const Icon = STEP_ICONS[idx] ?? ShieldCheck;
            const isLastOdd =
              idx === content.steps.length - 1 &&
              content.steps.length % 2 === 1;

            return (
              <Card
                key={step.id}
                className={cn(isLastOdd && "md:col-span-2")}
              >
                <CardHeader className="pb-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2.5">
                      <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-accent text-[var(--brand-text)]">
                        <Icon aria-hidden="true" className="size-4" />
                      </div>
                      <span className="text-xs font-bold tracking-wider text-[var(--brand-text)] tabular-nums">
                        {step.stepNumber}
                      </span>
                    </div>
                    <Badge
                      variant="secondary"
                      className="h-auto rounded-full px-2.5 py-0.5 text-xs font-medium"
                    >
                      {step.badge}
                    </Badge>
                  </div>
                  <CardTitle className="pt-2 text-base font-semibold">
                    <h3>{step.title}</h3>
                  </CardTitle>
                  <CardDescription className="leading-relaxed">
                    {step.summary}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <ul
                    className={cn(
                      "space-y-2 text-sm text-foreground/90",
                      isLastOdd && "md:grid md:grid-cols-2 md:gap-x-6 md:space-y-0 md:gap-y-2"
                    )}
                  >
                    {step.bullets.map((bullet) => (
                      <li key={bullet} className="flex items-start gap-2.5">
                        <CheckCircle2
                          aria-hidden="true"
                          className="mt-0.5 size-4 shrink-0 text-[var(--brand-text)]"
                        />
                        <span className="leading-relaxed">{bullet}</span>
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </section>

      {/* Verdict colors and recommended actions */}
      <section aria-labelledby="how-verdicts-heading" className="space-y-4">
        <div className="space-y-1">
          <h2
            id="how-verdicts-heading"
            className="text-lg font-semibold tracking-tight text-foreground sm:text-xl"
          >
            {content.verdictsTitle}
          </h2>
          <p className="max-w-3xl text-sm text-muted-foreground">
            {content.verdictsSubtitle}
          </p>
        </div>

        <div className="grid grid-cols-1 gap-4">
          {content.verdicts.map((item) => {
            const style = VERDICT_STYLES[item.verdict];
            return (
              <Card key={item.verdict} className="overflow-hidden py-0">
                <div
                  className={cn(
                    "flex flex-wrap items-center justify-between gap-2 border-b px-4 py-3 sm:px-5",
                    style.bannerClass
                  )}
                >
                  <div className="flex flex-wrap items-center gap-2.5">
                    <VerdictBadge
                      verdict={item.verdict}
                      label={item.title}
                      className="bg-card/90 shadow-2xs"
                    />
                    <h3 className="text-sm font-semibold sm:text-base">
                      {item.actionTitle}
                    </h3>
                  </div>
                </div>

                <CardContent className="grid grid-cols-1 gap-4 py-4 sm:px-5 md:grid-cols-3">
                  <div className="space-y-1">
                    <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      {content.verdictColWhen}
                    </div>
                    <p className="text-sm leading-relaxed text-foreground/90">
                      {item.whenShown}
                    </p>
                  </div>

                  <div className="space-y-1">
                    <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      {content.verdictColAction}
                    </div>
                    <p className="text-sm leading-relaxed text-foreground/90">
                      {item.actionDetails}
                    </p>
                  </div>

                  <div className="space-y-1">
                    <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      {content.verdictColSigning}
                    </div>
                    <p className="text-sm font-medium leading-relaxed text-foreground">
                      {item.signingRule}
                    </p>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </section>

      {/* Supporting workflow */}
      <section aria-labelledby="how-workflow-heading" className="space-y-4">
        <div className="space-y-1">
          <h2
            id="how-workflow-heading"
            className="text-lg font-semibold tracking-tight text-foreground sm:text-xl"
          >
            {content.workflowTitle}
          </h2>
          <p className="max-w-3xl text-sm text-muted-foreground">
            {content.workflowSubtitle}
          </p>
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {content.workflowItems.map((wf, idx) => {
            const Icon = WORKFLOW_ICONS[idx] ?? ShieldCheck;
            return (
              <Card key={wf.title}>
                <CardHeader className="pb-2">
                  <div className="flex size-9 items-center justify-center rounded-xl bg-accent text-[var(--brand-text)]">
                    <Icon aria-hidden="true" className="size-4" />
                  </div>
                  <CardTitle className="pt-2 text-base font-semibold">
                    <h3>{wf.title}</h3>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm leading-relaxed text-muted-foreground">
                    {wf.description}
                  </p>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </section>

      {/* CTA Banner */}
      <Card className="border-primary/25 bg-accent/45">
        <CardContent className="flex flex-col gap-4 py-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0 space-y-1">
            <h2 className="text-base font-semibold text-foreground sm:text-lg">
              {content.ctaTitle}
            </h2>
            <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground">
              {content.ctaDescription}
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-2">
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
            <Link
              href="/help"
              className={cn(
                buttonVariants({ variant: "outline" }),
                "min-h-11 rounded-xl bg-card px-4 sm:min-h-9"
              )}
            >
              <span>{info.common.openHelpCta}</span>
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
