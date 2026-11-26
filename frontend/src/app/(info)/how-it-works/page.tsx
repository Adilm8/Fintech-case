"use client";

import Link from "next/link";
import { InfoPageHeader } from "@/components/info/InfoPageHeader";
import { VerificationFlowDiagram } from "@/components/info/VerificationFlowDiagram";
import { VerdictBadge } from "@/components/VerdictBadge";
import { buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useInfoT } from "@/i18n/info";
import { IS_PROD } from "@/lib/mode";
import { cn } from "cn";

export default function HowItWorksPage() {
  const { info, appT } = useInfoT();
  const content = info.howItWorks;
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

      {/* Architecture / Flow Diagram */}
      <section aria-labelledby="how-diagram-heading">
        <Card>
          <CardHeader className="border-b border-border pb-3">
            <CardTitle>
              <h2 id="how-diagram-heading">{content.diagramTitle}</h2>
            </CardTitle>
            <CardDescription>{content.diagramSubtitle}</CardDescription>
          </CardHeader>
          <CardContent>
            <VerificationFlowDiagram />
          </CardContent>
        </Card>
      </section>

      {/* Step-by-step checks */}
      <section aria-labelledby="how-steps-heading" className="space-y-3">
        <div className="space-y-0.5">
          <h2 id="how-steps-heading" className="ui-section-title">
            {content.stepsTitle}
          </h2>
          <p className="max-w-3xl text-[13px] leading-5 text-muted-foreground">
            {content.stepsSubtitle}
          </p>
        </div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {content.steps.map((step, idx) => {
            const isLastOdd =
              idx === content.steps.length - 1 &&
              content.steps.length % 2 === 1;

            return (
              <div
                key={step.id}
                className={cn(
                  "ui-panel space-y-2.5 p-4",
                  isLastOdd && "md:col-span-2"
                )}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-mono text-xs font-medium tabular-nums text-muted-foreground">
                    {step.stepNumber}
                  </span>
                  <span className="ui-tag">{step.badge}</span>
                </div>
                <div className="space-y-1">
                  <h3 className="text-sm font-semibold text-foreground">
                    {step.title}
                  </h3>
                  <p className="text-[13px] leading-5 text-muted-foreground">
                    {step.summary}
                  </p>
                </div>
                <ul
                  className={cn(
                    "list-disc space-y-1.5 pl-4 text-sm leading-5 text-[var(--text-secondary)]",
                    isLastOdd &&
                      "md:grid md:grid-cols-2 md:gap-x-6 md:gap-y-1.5 md:space-y-0"
                  )}
                >
                  {step.bullets.map((bullet) => (
                    <li key={bullet}>{bullet}</li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      </section>

      {/* Verdict reference table */}
      <section aria-labelledby="how-verdicts-heading" className="space-y-3">
        <div className="space-y-0.5">
          <h2 id="how-verdicts-heading" className="ui-section-title">
            {content.verdictsTitle}
          </h2>
          <p className="max-w-3xl text-[13px] leading-5 text-muted-foreground">
            {content.verdictsSubtitle}
          </p>
        </div>

        <div className="ui-panel overflow-hidden">
          <div className="divide-y divide-border md:hidden">
            {content.verdicts.map((item) => (
              <div key={item.verdict} className="space-y-2.5 p-4">
                <div className="space-y-0.5">
                  <VerdictBadge verdict={item.verdict} label={item.title} />
                  <h3 className="text-sm font-semibold text-foreground">
                    {item.actionTitle}
                  </h3>
                </div>
                <div className="space-y-2 text-sm">
                  <div className="space-y-0.5">
                    <div className="ui-label-meta">
                      {content.verdictColWhen}
                    </div>
                    <p className="leading-5 text-[var(--text-secondary)]">
                      {item.whenShown}
                    </p>
                  </div>
                  <div className="space-y-0.5">
                    <div className="ui-label-meta">
                      {content.verdictColAction}
                    </div>
                    <p className="leading-5 text-[var(--text-secondary)]">
                      {item.actionDetails}
                    </p>
                  </div>
                  <div className="space-y-0.5">
                    <div className="ui-label-meta">
                      {content.verdictColSigning}
                    </div>
                    <p className="font-medium leading-5 text-foreground">
                      {item.signingRule}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div className="hidden md:block">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="w-[22%] pl-4">
                    {appT.history.colVerdict}
                  </TableHead>
                  <TableHead className="w-[26%]">
                    {content.verdictColWhen}
                  </TableHead>
                  <TableHead className="w-[28%]">
                    {content.verdictColAction}
                  </TableHead>
                  <TableHead className="w-[24%] pr-4">
                    {content.verdictColSigning}
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {content.verdicts.map((item) => (
                  <TableRow key={item.verdict} className="align-top">
                    <TableCell className="pl-4 whitespace-normal">
                      <VerdictBadge verdict={item.verdict} label={item.title} />
                      <div className="mt-1 text-xs font-medium text-foreground">
                        {item.actionTitle}
                      </div>
                    </TableCell>
                    <TableCell className="whitespace-normal text-[var(--text-secondary)]">
                      {item.whenShown}
                    </TableCell>
                    <TableCell className="whitespace-normal text-[var(--text-secondary)]">
                      {item.actionDetails}
                    </TableCell>
                    <TableCell className="pr-4 whitespace-normal font-medium text-foreground">
                      {item.signingRule}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      </section>

      {/* Supporting workflow */}
      <section aria-labelledby="how-workflow-heading" className="space-y-3">
        <div className="space-y-0.5">
          <h2 id="how-workflow-heading" className="ui-section-title">
            {content.workflowTitle}
          </h2>
          <p className="max-w-3xl text-[13px] leading-5 text-muted-foreground">
            {content.workflowSubtitle}
          </p>
        </div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          {content.workflowItems.map((wf) => (
            <div key={wf.title} className="ui-panel space-y-1.5 p-4">
              <h3 className="text-sm font-semibold text-foreground">
                {wf.title}
              </h3>
              <p className="text-sm leading-5 text-[var(--text-secondary)]">
                {wf.description}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* Footer navigation panel */}
      <div className="ui-panel flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 space-y-0.5">
          <h2 className="ui-section-title">{content.ctaTitle}</h2>
          <p className="max-w-2xl text-[13px] leading-5 text-muted-foreground">
            {content.ctaDescription}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <Link
            href={appHomeHref}
            className={cn(
              buttonVariants({ variant: "outline" }),
              "min-h-10 sm:min-h-9"
            )}
          >
            {info.common.openQueueCta}
          </Link>
          <Link
            href="/help"
            className={cn(
              buttonVariants({ variant: "outline" }),
              "min-h-10 sm:min-h-9"
            )}
          >
            {info.common.openHelpCta}
          </Link>
        </div>
      </div>
    </div>
  );
}
