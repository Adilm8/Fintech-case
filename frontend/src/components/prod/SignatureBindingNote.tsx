"use client";

import type { Lang } from "@/i18n";

export interface SignatureBindingLabels {
  signingDocument: string;
  check: string;
  rules: string;
}

export const SIGNATURE_BINDING_LABELS: Record<Lang, SignatureBindingLabels> = {
  ru: {
    signingDocument: "Подписывается документ",
    check: "проверка",
    rules: "правила",
  },
  kk: {
    signingDocument: "Қол қойылатын құжат",
    check: "тексеру",
    rules: "ережелер",
  },
  en: {
    signingDocument: "Document being signed",
    check: "check",
    rules: "rules",
  },
};

export interface SignatureBindingNoteProps {
  documentDigest: string;
  checkId: string;
  rulesetVersion: string;
  labels: SignatureBindingLabels;
  signerNote?: string;
  className?: string;
}

export function formatShortDigest(digest: string): string {
  const trimmed = digest.trim();
  if (trimmed.length <= 15) {
    return trimmed;
  }
  return `${trimmed.slice(0, 8)}…${trimmed.slice(-6)}`;
}

export function SignatureBindingNote({
  documentDigest,
  checkId,
  rulesetVersion,
  labels,
  signerNote,
  className,
}: SignatureBindingNoteProps) {
  const shortDigest = formatShortDigest(documentDigest);

  return (
    <div
      className={
        className
          ? `space-y-0.5 text-[11px] leading-snug text-muted-foreground break-words ${className}`
          : "space-y-0.5 text-[11px] leading-snug text-muted-foreground break-words"
      }
      title={documentDigest}
    >
      <p>
        {labels.signingDocument}:{" "}
        <span
          className="font-mono tabular-nums text-foreground/80"
          title={documentDigest}
        >
          {shortDigest}
        </span>
        , {labels.check}{" "}
        <span className="font-mono tabular-nums">{checkId}</span>,{" "}
        {labels.rules}{" "}
        <span className="font-mono tabular-nums">{rulesetVersion}</span>
      </p>
      {signerNote && <p className="text-muted-foreground">{signerNote}</p>}
    </div>
  );
}
