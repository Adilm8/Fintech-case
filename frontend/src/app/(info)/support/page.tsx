"use client";

import { useId, useState, type FormEvent } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Headphones,
  Info,
  Mail,
  Phone,
  RotateCcw,
  Send,
} from "lucide-react";
import { InfoNavLinks } from "@/components/info/InfoNavLinks";
import { InfoPageHeader } from "@/components/info/InfoPageHeader";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
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
    <div className="space-y-6 sm:space-y-8">
      <InfoPageHeader
        icon={Headphones}
        title={content.title}
        subtitle={content.subtitle}
        badge={info.common.prototypeBadge}
      />

      <Alert className="rounded-2xl border-amber-300/80 bg-amber-50/85 px-4 py-3.5 text-amber-950">
        <Info aria-hidden="true" className="size-4 text-amber-700" />
        <AlertTitle className="font-semibold text-amber-950">
          {content.prototypeBannerTitle}
        </AlertTitle>
        <AlertDescription className="text-amber-900">
          {content.prototypeBannerDescription}
        </AlertDescription>
      </Alert>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Local Support Form */}
        <section
          aria-labelledby="support-form-heading"
          className="lg:col-span-7"
        >
          <Card>
            <CardHeader className="border-b border-border pb-4">
              <CardTitle className="text-base sm:text-lg">
                <h2 id="support-form-heading">{content.formTitle}</h2>
              </CardTitle>
              <CardDescription>{content.formDescription}</CardDescription>
            </CardHeader>

            <CardContent className="pt-4">
              <form onSubmit={handleSubmit} noValidate className="space-y-4">
                {errorText && (
                  <Alert
                    variant="destructive"
                    className="rounded-xl border-red-300 bg-red-50/90"
                  >
                    <AlertCircle aria-hidden="true" className="size-4" />
                    <AlertDescription>{errorText}</AlertDescription>
                  </Alert>
                )}

                {submitted && (
                  <Alert className="rounded-xl border-[#00AB75]/35 bg-[#E8F8F2] text-[#064A34]">
                    <CheckCircle2
                      aria-hidden="true"
                      className="size-4 text-[var(--brand-text)]"
                    />
                    <AlertTitle className="font-semibold text-[#064A34]">
                      {content.submittedBannerTitle}
                    </AlertTitle>
                    <AlertDescription className="text-[#064A34]/90">
                      {content.submittedBannerDescription}
                    </AlertDescription>
                  </Alert>
                )}

                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
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
                      className="h-11 rounded-xl bg-background sm:h-10"
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
                      className="h-11 rounded-xl bg-background sm:h-10"
                    />
                  </div>
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor={topicId}>{content.topicLabel}</Label>
                  <select
                    id={topicId}
                    value={topic}
                    onChange={(e) => setTopic(e.target.value)}
                    className="h-11 w-full rounded-xl border border-input bg-background px-3 py-1.5 text-sm text-foreground transition-colors outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 sm:h-10"
                  >
                    {content.topics.map((item) => (
                      <option key={item.value} value={item.value}>
                        {item.label}
                      </option>
                    ))}
                  </select>
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
                    className="min-h-32 rounded-xl bg-background"
                  />
                </div>

                <div className="flex flex-col gap-2 pt-1 sm:flex-row sm:items-center">
                  <Button
                    type="submit"
                    className="min-h-11 gap-2 rounded-xl px-5 sm:min-h-10"
                  >
                    <Send aria-hidden="true" className="size-4" />
                    <span>{content.submitButton}</span>
                  </Button>

                  <Button
                    type="button"
                    variant="outline"
                    onClick={handleReset}
                    className="min-h-11 gap-2 rounded-xl px-4 sm:min-h-10"
                  >
                    <RotateCcw aria-hidden="true" className="size-4" />
                    <span>{content.resetButton}</span>
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        </section>

        {/* Placeholder Contacts & Quick Links */}
        <aside className="space-y-5 lg:col-span-5">
          <Card>
            <CardHeader className="border-b border-border pb-4">
              <CardTitle className="text-base sm:text-lg">
                <h2>{content.contactsTitle}</h2>
              </CardTitle>
              <CardDescription>{content.contactsDescription}</CardDescription>
            </CardHeader>

            <CardContent className="space-y-3 pt-4">
              <div className="flex items-start gap-3 rounded-xl border border-border bg-background/70 p-3.5">
                <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent text-[var(--brand-text)]">
                  <Mail aria-hidden="true" className="size-4" />
                </div>
                <div className="min-w-0 space-y-0.5">
                  <div className="text-xs font-medium text-muted-foreground">
                    {content.emailContactLabel}
                  </div>
                  <div className="font-mono text-sm font-semibold text-foreground break-all">
                    {content.emailContactValue}
                  </div>
                </div>
              </div>

              <div className="flex items-start gap-3 rounded-xl border border-border bg-background/70 p-3.5">
                <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent text-[var(--brand-text)]">
                  <Phone aria-hidden="true" className="size-4" />
                </div>
                <div className="min-w-0 space-y-0.5">
                  <div className="text-xs font-medium text-muted-foreground">
                    {content.phoneContactLabel}
                  </div>
                  <div className="text-sm font-semibold text-foreground break-words">
                    {content.phoneContactValue}
                  </div>
                </div>
              </div>

              <div className="flex items-start gap-3 rounded-xl border border-border bg-background/70 p-3.5">
                <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted text-foreground/75">
                  <Clock aria-hidden="true" className="size-4" />
                </div>
                <div className="min-w-0 space-y-0.5">
                  <div className="text-xs font-medium text-muted-foreground">
                    {content.hoursLabel}
                  </div>
                  <div className="text-sm font-medium text-foreground">
                    {content.hoursValue}
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">
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
