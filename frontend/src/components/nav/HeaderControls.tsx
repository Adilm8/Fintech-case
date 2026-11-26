"use client";

import Link from "next/link";
import { Building2 } from "lucide-react";
import { LANG_OPTIONS, type Lang } from "@/i18n";
import { cn } from "cn";

export interface BrandLogoProps {
  href: string;
  name: string;
  onClick?: () => void;
  className?: string;
}

export function BrandLogo({ href, name, onClick, className }: BrandLogoProps) {
  return (
    <Link
      href={href}
      onClick={onClick}
      aria-label={name}
      className={cn(
        "inline-flex min-h-10 min-w-0 shrink-0 items-center gap-2.5 rounded-[10px] text-left transition-opacity hover:opacity-85 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring md:min-h-8",
        className
      )}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/logo.svg"
        alt=""
        width={32}
        height={32}
        className="size-8 shrink-0"
      />
      <span className="hidden truncate text-[16px] font-semibold tracking-[-0.015em] text-foreground md:inline">
        {name}
      </span>
    </Link>
  );
}

export interface CompanyChipProps {
  name: string;
  className?: string;
}

export function CompanyChip({ name, className }: CompanyChipProps) {
  return (
    <div title={name} className={cn("hdr-company-chip", className)}>
      <Building2
        aria-hidden="true"
        className="size-3.5 shrink-0 text-muted-foreground"
      />
      <span className="truncate">{name}</span>
    </div>
  );
}

export interface LanguageSwitchProps {
  lang: Lang;
  onChange: (nextLang: Lang) => void;
  ariaLabel: string;
  className?: string;
}

export function LanguageSwitch({
  lang,
  onChange,
  ariaLabel,
  className,
}: LanguageSwitchProps) {
  return (
    <div
      className={cn("hdr-lang-switch", className)}
      role="group"
      aria-label={ariaLabel}
    >
      {LANG_OPTIONS.map((option) => {
        const isSelected = lang === option.code;
        return (
          <button
            key={option.code}
            type="button"
            aria-pressed={isSelected}
            onClick={() => onChange(option.code)}
            className="hdr-lang-btn focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
