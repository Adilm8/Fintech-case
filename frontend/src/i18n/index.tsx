"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import type { TrustedInfo } from "@/lib/types";
import { en } from "./en";
import { kk } from "./kk";
import { ru, type Dictionary, type PluralForms } from "./ru";

export type Lang = "ru" | "kk" | "en";

export const LANG_STORAGE_KEY = "business-shield.lang";

export const LANG_OPTIONS: readonly { code: Lang; label: string }[] = [
  { code: "ru", label: "РУС" },
  { code: "kk", label: "ҚАЗ" },
  { code: "en", label: "ENG" },
] as const;

const LOCALE_BY_LANG: Record<Lang, string> = {
  ru: "ru-RU",
  kk: "kk-KZ",
  en: "en-US",
};

const DICTIONARIES: Record<Lang, Dictionary> = { ru, kk, en };

function isLang(value: unknown): value is Lang {
  return value === "ru" || value === "kk" || value === "en";
}

let cachedClientLang: Lang | null = null;
const langListeners = new Set<() => void>();

function readStoredLang(): Lang {
  if (typeof window === "undefined") return "ru";
  try {
    const saved = window.localStorage.getItem(LANG_STORAGE_KEY);
    if (isLang(saved)) return saved;
  } catch {
    // Ignore storage access errors in restricted browsing contexts.
  }
  return "ru";
}

function getClientLangSnapshot(): Lang {
  if (cachedClientLang === null) {
    cachedClientLang = readStoredLang();
  }
  return cachedClientLang;
}

function getServerLangSnapshot(): Lang {
  return "ru";
}

function subscribeLangStore(listener: () => void): () => void {
  langListeners.add(listener);
  if (typeof window === "undefined") {
    return () => {
      langListeners.delete(listener);
    };
  }
  const onStorage = (event: StorageEvent) => {
    if (event.key !== LANG_STORAGE_KEY) return;
    const next: Lang = isLang(event.newValue) ? event.newValue : "ru";
    if (next !== cachedClientLang) {
      cachedClientLang = next;
      langListeners.forEach((cb) => cb());
    }
  };
  window.addEventListener("storage", onStorage);
  return () => {
    langListeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

export function getCurrentLang(): Lang {
  return typeof window === "undefined" ? "ru" : getClientLangSnapshot();
}

export function setCurrentLang(nextLang: Lang): void {
  cachedClientLang = nextLang;
  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(LANG_STORAGE_KEY, nextLang);
    } catch {
      // Ignore storage write errors.
    }
  }
  langListeners.forEach((cb) => cb());
}

export function getDictionary(lang: Lang): Dictionary {
  return DICTIONARIES[lang] ?? ru;
}

export function interpolate(
  template: string,
  params?: Record<string, string | number>
): string {
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (match, key: string) =>
    key in params ? String(params[key]) : match
  );
}

export function formatPlural(
  lang: Lang,
  count: number,
  forms: PluralForms
): string {
  let template: string;
  if (lang === "ru") {
    const abs = Math.abs(count) % 100;
    const mod10 = abs % 10;
    if (abs >= 11 && abs <= 19) {
      template = forms.many;
    } else if (mod10 === 1) {
      template = forms.one;
    } else if (mod10 >= 2 && mod10 <= 4) {
      template = forms.few;
    } else {
      template = forms.many;
    }
  } else if (lang === "en") {
    template = Math.abs(count) === 1 ? forms.one : forms.many;
  } else {
    template = forms.one;
  }
  return interpolate(template, { count });
}

export function formatMoneyForLang(
  amount: number | null | undefined,
  lang: Lang
): string {
  if (amount === null || amount === undefined || Number.isNaN(amount)) {
    return "—";
  }
  const hasFraction = Math.abs(amount % 1) > 0.001;
  const formatted = new Intl.NumberFormat(LOCALE_BY_LANG[lang], {
    minimumFractionDigits: hasFraction ? 2 : 0,
    maximumFractionDigits: hasFraction ? 2 : 0,
  })
    .format(amount)
    .replace(/\u00a0/g, " ");

  return `${formatted} ₸`;
}

export function formatDateForLang(
  dateStr: string | null | undefined,
  lang: Lang
): string {
  if (!dateStr) return "—";

  let parsed: Date;
  const dateOnlyMatch = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateStr.trim());
  if (dateOnlyMatch) {
    parsed = new Date(
      Number(dateOnlyMatch[1]),
      Number(dateOnlyMatch[2]) - 1,
      Number(dateOnlyMatch[3])
    );
  } else {
    parsed = new Date(dateStr);
  }

  if (Number.isNaN(parsed.getTime())) {
    return dateStr;
  }

  return new Intl.DateTimeFormat(LOCALE_BY_LANG[lang], {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(parsed);
}

export function formatTrustedBannerForLang(
  trustedInfo: TrustedInfo | null | undefined,
  lang: Lang
): string {
  const dict = getDictionary(lang);
  const base = trustedInfo?.decided_at
    ? interpolate(dict.check.trustedConfirmedWithDate, {
        date: formatDateForLang(trustedInfo.decided_at, lang),
      })
    : dict.check.trustedConfirmedBase;
  const comment = trustedInfo?.director_comment?.trim();
  return comment ? `${base}: ${comment}` : base;
}

export interface LangContextValue {
  lang: Lang;
  t: Dictionary;
  setLang: (nextLang: Lang) => void;
  formatMoney: (amount: number | null | undefined) => string;
  formatDate: (dateStr: string | null | undefined) => string;
  interpolate: typeof interpolate;
  plural: (count: number, forms: PluralForms) => string;
  formatTrustedBanner: (trustedInfo: TrustedInfo | null | undefined) => string;
}

const LangContext = createContext<LangContextValue | null>(null);

export function LangProvider({ children }: { children: ReactNode }) {
  const lang = useSyncExternalStore(
    subscribeLangStore,
    getClientLangSnapshot,
    getServerLangSnapshot
  );

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const setLang = useCallback((nextLang: Lang) => {
    setCurrentLang(nextLang);
  }, []);

  const formatMoney = useCallback(
    (amount: number | null | undefined) => formatMoneyForLang(amount, lang),
    [lang]
  );

  const formatDate = useCallback(
    (dateStr: string | null | undefined) => formatDateForLang(dateStr, lang),
    [lang]
  );

  const plural = useCallback(
    (count: number, forms: PluralForms) => formatPlural(lang, count, forms),
    [lang]
  );

  const formatTrustedBanner = useCallback(
    (trustedInfo: TrustedInfo | null | undefined) =>
      formatTrustedBannerForLang(trustedInfo, lang),
    [lang]
  );

  const value = useMemo<LangContextValue>(
    () => ({
      lang,
      t: getDictionary(lang),
      setLang,
      formatMoney,
      formatDate,
      interpolate,
      plural,
      formatTrustedBanner,
    }),
    [lang, setLang, formatMoney, formatDate, plural, formatTrustedBanner]
  );

  return <LangContext.Provider value={value}>{children}</LangContext.Provider>;
}

export function useT(): LangContextValue {
  const ctx = useContext(LangContext);
  if (!ctx) {
    throw new Error("useT must be used inside LangProvider");
  }
  return ctx;
}

export type { Dictionary, PluralForms };
