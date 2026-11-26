"use client";

import { useMemo } from "react";
import { useT, type Dictionary, type Lang } from "@/i18n";
import { infoEn } from "./en";
import { infoKk } from "./kk";
import { infoRu } from "./ru";
import type { InfoDictionary, InfoRouteKey } from "./types";

export const INFO_DICTIONARIES: Record<Lang, InfoDictionary> = {
  ru: infoRu,
  kk: infoKk,
  en: infoEn,
};

export function getInfoDictionary(lang: Lang): InfoDictionary {
  return INFO_DICTIONARIES[lang] ?? infoRu;
}

export interface InfoLangContextValue {
  lang: Lang;
  mounted: boolean;
  setLang: (nextLang: Lang) => void;
  info: InfoDictionary;
  appT: Dictionary;
  interpolate: (
    template: string,
    params?: Record<string, string | number>
  ) => string;
}

/**
 * Reads the exact same SSR-safe LangProvider context & localStorage store as useT(),
 * returning localized strings for the (info) product pages without hydration mismatches.
 */
export function useInfoT(): InfoLangContextValue {
  const { lang, mounted, setLang, t, interpolate } = useT();

  return useMemo(
    () => ({
      lang,
      mounted,
      setLang,
      info: getInfoDictionary(lang),
      appT: t,
      interpolate,
    }),
    [interpolate, lang, mounted, setLang, t]
  );
}

export type { InfoDictionary, InfoRouteKey };
