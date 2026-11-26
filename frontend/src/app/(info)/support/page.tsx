"use client";

import { useId, useState, type FormEvent } from "react";
import { ChevronDown } from "lucide-react";
import { InfoNavLinks } from "@/components/info/InfoNavLinks";
import { InfoPageHeader } from "@/components/info/InfoPageHeader";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useInfoT } from "@/i18n/info";
import { notify } from "@/lib/toast";

const SIMPLE_EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function SupportPage() {
  const { info } = useInfoT();
  const content = info.support;

  const nameId = useId();
  const emailId = useId();
  const topicId = useId();
  const messageId = useId();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [topic, setTopic] = useState("verdict");
  const [message, setMessage] = useState("");
  const [errorText, setErrorText] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const trimmedName = name.trim();
    const trimmedEmail = email.trim();
    const trimmedMessage = message.trim();

    if (!trimmedName || !trimmedEmail || !trimmedMessage) {
      setErrorText(content.validationError);
      setSubmitted(false);
      return;
    }

    if (!SIMPLE_EMAIL_RE.test(trimmedEmail)) {
      setErrorText(content.emailValidationError);
      setSubmitted(false);
      return;
    }

    // Prototype-only local feedback: intentionally sends nothing to any backend or third party.
    setErrorText(null);
    setSubmitted(true);
    notify.success(content.toastSuccessTitle, content.toastSuccessDescription);
  };

  const handleReset = () => {
    setName("");
    setEmail("");
    setTopic("verdict");
    setMessage("");
    setErrorText(null);
    setSubmitted(false);
  };

  return (
    <div className="space-y-5">
      <InfoPageHeader
        title={content.title}
        subtitle={content.subtitle}
        badge={info.common.prototypeBadge}
      />

      <div role="note" className="ui-notice ui-notice-warn space-y-0.5">
        <div className="text-[13px] font-semibold text-foreground">
          {content.prototypeBannerTitle}
        </div>
        <p className="text-xs leading-5 text-[var(--text-secondary)]">
          {content.prototypeBannerDescription}
        </p>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        {/* Local Support Form */}
        <section
          aria-labelledby="support-form-heading"
          className="lg:col-span-7"
        >
          <Card>
            <CardHeader className="border-b border-border pb-3">
              <CardTitle>
                <h2 id="support-form-heading">{content.formTitle}</h2>
              </CardTitle>
              <CardDescription>{content.formDescription}</CardDescription>
            </CardHeader>

            <CardContent>
              <form onSubmit={handleSubmit} noValidate className="space-y-4">
                {errorText && (
                  <div
                    role="alert"
                    className="ui-notice ui-notice-danger py-2 text-xs text-foreground"
                  >
                    {errorText}
                  </div>
                )}

                {submitted && (
                  <div
                    role="status"
                    className="ui-notice ui-notice-ok space-y-0.5"
                  >
                    <div className="text-[13px] font-semibold text-foreground">
                      {content.submittedBannerTitle}
                    </div>
                    <p className="text-xs leading-5 text-[var(--text-secondary)]">
                      {content.submittedBannerDescription}
                    </p>
                  </div>
                )}

                <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2">
                  <div className="space-y-1.5">
                    <Label htmlFor={nameId}>{content.nameLabel}</Label>
                    <Input
                      id={nameId}
                      type="text"
                      value={name}
                      onChange={(e) => {
                        setName(e.target.value);
                        if (errorText) setErrorText(null);
                      }}
                      placeholder={content.namePlaceholder}
                      autoComplete="off"
                      required
                      className="h-10 bg-card sm:h-9"
                    />
                  </div>

                  <div className="space-y-1.5">
                    <Label htmlFor={emailId}>{content.emailLabel}</Label>
                    <Input
                      id={emailId}
                      type="email"
                      value={email}
                      onChange={(e) => {
                        setEmail(e.target.value);
                        if (errorText) setErrorText(null);
                      }}
                      placeholder={content.emailPlaceholder}
                      autoComplete="off"
                      required
                      className="h-10 bg-card sm:h-9"
                    />
                  </div>
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor={topicId}>{content.topicLabel}</Label>
                  <div className="relative">
                    <select
                      id={topicId}
                      value={topic}
                      onChange={(e) => setTopic(e.target.value)}
                      className="ui-select h-10 w-full appearance-none sm:h-9"
                    >
                      {content.topics.map((item) => (
                        <option key={item.value} value={item.value}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                    <ChevronDown
                      aria-hidden="true"
                      className="pointer-events-none absolute top-1/2 right-2.5 size-4 -translate-y-1/2 text-muted-foreground"
                    />
                  </div>
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor={messageId}>{content.messageLabel}</Label>
                  <Textarea
                    id={messageId}
                    rows={5}
                    value={message}
                    onChange={(e) => {
                      setMessage(e.target.value);
                      if (errorText) setErrorText(null);
                    }}
                    placeholder={content.messagePlaceholder}
                    required
                    className="min-h-32 bg-card"
                  />
                </div>

                <div className="flex flex-col gap-2 pt-0.5 sm:flex-row sm:items-center">
                  <Button
                    type="submit"
                    className="min-h-10 sm:min-h-9"
                  >
                    {content.submitButton}
                  </Button>

                  <Button
                    type="button"
                    variant="outline"
                    onClick={handleReset}
                    className="min-h-10 sm:min-h-9"
                  >
                    {content.resetButton}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        </section>

        {/* Contacts summary list & Quick Links */}
        <aside className="space-y-4 lg:col-span-5">
          <Card>
            <CardHeader className="border-b border-border pb-3">
              <CardTitle>
                <h2>{content.contactsTitle}</h2>
              </CardTitle>
              <CardDescription>{content.contactsDescription}</CardDescription>
            </CardHeader>

            <CardContent>
              <dl className="ui-dl">
                <div className="ui-dl-row">
                  <dt className="ui-dt">{content.emailContactLabel}</dt>
                  <dd className="ui-dd font-mono text-xs sm:text-sm break-all">
                    {content.emailContactValue}
                  </dd>
                </div>
                <div className="ui-dl-row">
                  <dt className="ui-dt">{content.phoneContactLabel}</dt>
                  <dd className="ui-dd font-medium">
                    {content.phoneContactValue}
                  </dd>
                </div>
                <div className="ui-dl-row">
                  <dt className="ui-dt">{content.hoursLabel}</dt>
                  <dd className="ui-dd">{content.hoursValue}</dd>
                </div>
              </dl>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="border-b border-border pb-3">
              <CardTitle>
                <h2>{content.quickLinksTitle}</h2>
              </CardTitle>
              <CardDescription>{content.quickLinksDescription}</CardDescription>
            </CardHeader>
            <CardContent>
              <InfoNavLinks variant="inline" />
            </CardContent>
          </Card>
        </aside>
      </div>
    </div>
  );
}
