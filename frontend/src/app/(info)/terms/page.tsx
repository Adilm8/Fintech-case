"use client";

import Link from "next/link";
import { AlertTriangle, FileCheck2 } from "lucide-react";
import { InfoPageHeader } from "@/components/info/InfoPageHeader";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { useInfoT } from "@/i18n/info";
import { cn } from "cn";

export default function TermsPage() {
  const { info } = useInfoT();
  const content = info.terms;

  return (
    <div className="space-y-6 sm:space-y-8">
      <InfoPageHeader
        icon={FileCheck2}
        title={content.title}
        subtitle={content.subtitle}
        badge={info.common.prototypeBadge}
      />

      <Alert className="rounded-2xl border-amber-300/90 bg-amber-50/85 px-4 py-3.5 text-amber-950">
        <AlertTriangle aria-hidden="true" className="size-4 text-amber-700" />
        <AlertTitle className="font-semibold text-amber-950">
          {content.bannerTitle}
        </AlertTitle>
        <AlertDescription className="text-amber-900">
          {content.bannerDescription}
        </AlertDescription>
      </Alert>

      <Card>
        <CardHeader className="border-b border-border pb-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Badge
              variant="secondary"
              className="h-auto rounded-full px-3 py-1 text-xs font-medium"
            >
              {content.updatedLabel}
            </Badge>
            <div className="flex flex-wrap items-center gap-2">
              <Link
                href="/privacy"
                className={cn(
                  buttonVariants({ variant: "outline", size: "sm" }),
                  "rounded-lg"
                )}
              >
                {info.nav.privacy}
              </Link>
              <Link
                href="/security"
                className={cn(
                  buttonVariants({ variant: "outline", size: "sm" }),
                  "rounded-lg"
                )}
              >
                {info.nav.security}
              </Link>
            </div>
          </div>
        </CardHeader>

        <CardContent className="space-y-6 pt-5">
          {content.sections.map((section, idx) => (
            <div key={section.title}>
              {idx > 0 && <Separator className="mb-6" />}
              <section className="max-w-3xl space-y-2.5">
                <h2 className="text-base font-semibold tracking-tight text-foreground sm:text-lg">
                  {section.title}
                </h2>
                {section.paragraphs.map((paragraph) => (
                  <p
                    key={paragraph}
                    className="text-sm leading-relaxed text-foreground/90"
                  >
                    {paragraph}
                  </p>
                ))}
              </section>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
