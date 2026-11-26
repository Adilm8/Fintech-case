"use client";

import Link from "next/link";
import { InfoPageHeader } from "@/components/info/InfoPageHeader";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { useInfoT } from "@/i18n/info";

export default function TermsPage() {
  const { info } = useInfoT();
  const content = info.terms;

  return (
    <div className="space-y-5">
      <InfoPageHeader
        title={content.title}
        subtitle={content.subtitle}
        badge={info.common.prototypeBadge}
      />

      <div role="note" className="ui-notice ui-notice-warn space-y-0.5">
        <div className="text-[13px] font-semibold text-foreground">
          {content.bannerTitle}
        </div>
        <p className="text-xs leading-5 text-[var(--text-secondary)]">
          {content.bannerDescription}
        </p>
      </div>

      <Card>
        <CardHeader className="border-b border-border pb-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="ui-tag">{content.updatedLabel}</span>
            <div className="flex flex-wrap items-center gap-2">
              <Link
                href="/privacy"
                className={buttonVariants({ variant: "outline", size: "sm" })}
              >
                {info.nav.privacy}
              </Link>
              <Link
                href="/security"
                className={buttonVariants({ variant: "outline", size: "sm" })}
              >
                {info.nav.security}
              </Link>
            </div>
          </div>
        </CardHeader>

        <CardContent className="space-y-5">
          {content.sections.map((section, idx) => (
            <div key={section.title}>
              {idx > 0 && <Separator className="mb-5" />}
              <section className="max-w-3xl space-y-2">
                <h2 className="ui-section-title">{section.title}</h2>
                {section.paragraphs.map((paragraph) => (
                  <p
                    key={paragraph}
                    className="text-sm leading-6 text-[var(--text-secondary)]"
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
