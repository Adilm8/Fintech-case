import type { Lang } from "@/i18n";
import type {
  CheckResult,
  ComparisonField,
  MetricsResponse,
  NextAction,
  Signal,
  Verdict,
} from "./types";

export const LOCALE_BY_LANG: Record<Lang, string> = {
  ru: "ru-RU",
  kk: "kk-KZ",
  en: "en-US",
};

const NBSP = "\u00A0";

const EN_SHORT_MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
] as const;

function addThousandsSeparator(integerPart: string, sep: string): string {
  const negative = integerPart.startsWith("-");
  const digits = negative ? integerPart.slice(1) : integerPart;
  const grouped = digits.replace(/\B(?=(\d{3})+(?!\d))/g, sep);
  return negative ? `-${grouped}` : grouped;
}

export function formatDecimalForLang(
  value: number | null | undefined,
  lang: Lang,
  options?: { minFractionDigits?: number; maxFractionDigits?: number }
): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "—";
  }
  const minFrac = options?.minFractionDigits ?? 0;
  const maxFrac = options?.maxFractionDigits ?? minFrac;
  const fixed = value.toFixed(maxFrac);
  let [intPart, fracPart = ""] = fixed.split(".");
  if (fracPart && maxFrac > minFrac) {
    let end = fracPart.length;
    while (end > minFrac && fracPart[end - 1] === "0") {
      end -= 1;
    }
    fracPart = fracPart.slice(0, end);
  }
  if (intPart === "-0" && !fracPart) {
    intPart = "0";
  }

  const thousandsSep = lang === "en" ? "," : NBSP;
  const decimalSep = lang === "en" ? "." : ",";
  const groupedInt = addThousandsSeparator(intPart, thousandsSep);
  return fracPart ? `${groupedInt}${decimalSep}${fracPart}` : groupedInt;
}

export function formatIntegerForLang(
  value: number | null | undefined,
  lang: Lang
): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "—";
  }
  return formatDecimalForLang(Math.round(value), lang, {
    minFractionDigits: 0,
    maxFractionDigits: 0,
  });
}

export function formatPercentForLang(
  value: number | null | undefined,
  lang: Lang
): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "—";
  }
  const hasFraction = Math.abs(value % 1) >= 0.05;
  const formatted = formatDecimalForLang(value, lang, {
    minFractionDigits: hasFraction ? 1 : 0,
    maxFractionDigits: 1,
  });
  return `${formatted}%`;
}

export function formatMoneyForLang(
  amount: number | null | undefined,
  lang: Lang
): string {
  if (amount === null || amount === undefined || !Number.isFinite(amount)) {
    return "—";
  }
  const hasFraction = Math.abs(amount % 1) > 0.001;
  const formatted = formatDecimalForLang(amount, lang, {
    minFractionDigits: hasFraction ? 2 : 0,
    maxFractionDigits: hasFraction ? 2 : 0,
  });
  return `${formatted}${NBSP}₸`;
}

export function parseKztString(raw: string | null | undefined): number | null {
  if (!raw) return null;
  const stripped = raw
    .replace(/₸|KZT|тг\.?/gi, "")
    .replace(/[\s\u00A0\u202F]+/g, "")
    .trim();
  if (!stripped) return null;

  let normalized = stripped;
  const commaCount = (normalized.match(/,/g) ?? []).length;
  const dotCount = (normalized.match(/\./g) ?? []).length;
  if (commaCount > 0 && dotCount === 0) {
    // Distinguish EN thousands grouping (e.g. 1,360,000) from RU/KK decimal comma (e.g. 12,50).
    if (/^-?\d{1,3}(,\d{3})+$/.test(normalized)) {
      normalized = normalized.replace(/,/g, "");
    } else if (commaCount === 1) {
      normalized = normalized.replace(",", ".");
    }
  } else if (commaCount > 0 && dotCount > 0) {
    normalized = normalized.replace(/,/g, "");
  }

  if (!/^-?\d+(\.\d+)?$/.test(normalized)) {
    return null;
  }
  const num = Number(normalized);
  return Number.isFinite(num) ? num : null;
}

export function formatDateForLang(
  dateStr: string | null | undefined,
  lang: Lang
): string {
  if (!dateStr) return "—";

  const trimmed = dateStr.trim();

  // Year-month values like "2025-12"
  const ymMatch = /^(\d{4})-(\d{2})$/.exec(trimmed);
  if (ymMatch) {
    const year = Number(ymMatch[1]);
    const month = Number(ymMatch[2]);
    if (month >= 1 && month <= 12) {
      if (lang === "en") {
        return `${EN_SHORT_MONTHS[month - 1]} ${year}`;
      }
      return `${String(month).padStart(2, "0")}.${year}`;
    }
  }

  let day: number;
  let month: number;
  let year: number;

  const isoDateMatch = /^(\d{4})-(\d{2})-(\d{2})(?:$|T|\s)/.exec(trimmed);
  const dmyMatch = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec(trimmed);

  if (isoDateMatch) {
    year = Number(isoDateMatch[1]);
    month = Number(isoDateMatch[2]);
    day = Number(isoDateMatch[3]);
  } else if (dmyMatch) {
    day = Number(dmyMatch[1]);
    month = Number(dmyMatch[2]);
    year = Number(dmyMatch[3]);
  } else {
    const parsed = new Date(trimmed);
    if (Number.isNaN(parsed.getTime())) {
      return dateStr;
    }
    day = parsed.getDate();
    month = parsed.getMonth() + 1;
    year = parsed.getFullYear();
  }

  if (month < 1 || month > 12 || day < 1 || day > 31) {
    return dateStr;
  }

  if (lang === "en") {
    return `${day} ${EN_SHORT_MONTHS[month - 1]} ${year}`;
  }

  return `${String(day).padStart(2, "0")}.${String(month).padStart(2, "0")}.${year}`;
}

export function formatNumberForLang(
  value: number | null | undefined,
  lang: Lang,
  options?: Intl.NumberFormatOptions
): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "—";
  }
  return formatDecimalForLang(value, lang, {
    minFractionDigits: options?.minimumFractionDigits ?? 0,
    maxFractionDigits: options?.maximumFractionDigits ?? 0,
  });
}

/**
 * Normalizes embedded amounts (e.g. "1 360 000 ₸"), decimal ratios (e.g. "3.6" -> "3,6" in ru/kk),
 * and dates (dd.MM.yyyy / YYYY-MM-DD) inside backend-supplied strings for the active UI language.
 */
export function localizeBackendText(text: string, lang: Lang): string {
  if (!text) return text;

  // 1. Format embedded KZT amounts consistently per language with NBSP.
  let out = text.replace(
    /\b\d{1,3}(?:[\s\u00A0\u202F,]\d{3})+(?:[.,]\d{1,2})?\s*₸|\b\d+(?:[.,]\d{1,2})?\s*₸/g,
    (match) => {
      const parsed = parseKztString(match);
      return parsed !== null ? formatMoneyForLang(parsed, lang) : match;
    }
  );

  // 2. Format embedded dates (dd.MM.yyyy and YYYY-MM-DD) consistently per language.
  out = out.replace(/\b(\d{4}-\d{2}-\d{2})\b/g, (match) =>
    formatDateForLang(match, lang)
  );
  if (lang === "en") {
    out = out.replace(/\b(\d{2}\.\d{2}\.\d{4})\b/g, (match) =>
      formatDateForLang(match, lang)
    );
  }

  // 3. Convert decimal dots to commas in ru/kk (e.g. "в 3.6 раза" -> "в 3,6 раза"),
  // while leaving dates (dd.MM.yyyy or MM.yyyy) untouched.
  if (lang === "ru" || lang === "kk") {
    out = out.replace(
      /(?<!\d\.)\b(\d+)\.(\d{1,2})\b(?!\.\d)(?!\d)/g,
      "$1,$2"
    );
  }

  return out;
}

export function extractInvalidFieldMap(
  verdict: Verdict,
  signals: Signal[]
): Partial<Record<ComparisonField, string[]>> {
  if (verdict !== "invalid") return {};
  const map: Partial<Record<ComparisonField, string[]>> = {};

  const pushReason = (field: ComparisonField, reason: string) => {
    const existing = map[field] ?? [];
    if (reason && !existing.includes(reason)) {
      map[field] = [...existing, reason];
    } else if (!map[field]) {
      map[field] = existing;
    }
  };

  for (const signal of signals) {
    const reason = signal.reason?.trim() || signal.reason_ru;
    if (signal.rule_id === "invalid_bin") {
      pushReason("bin", reason);
    } else if (signal.rule_id === "invalid_iik") {
      pushReason("iik", reason);
    } else if (signal.rule_id === "invalid_bik") {
      pushReason("bik", reason);
    } else if (signal.rule_id === "iik_bank_code_vs_bik") {
      pushReason("iik", reason);
      pushReason("bik", reason);
    } else if (
      signal.evidence?.field === "bin" ||
      signal.evidence?.field === "iik" ||
      signal.evidence?.field === "bik"
    ) {
      pushReason(signal.evidence.field, reason);
    }
  }

  return map;
}

export function pickHeadline(
  result: Pick<CheckResult, "headline" | "headline_ru">,
  lang?: Lang
): string {
  const localized = result.headline?.trim();
  const raw = localized || result.headline_ru;
  return lang ? localizeBackendText(raw, lang) : raw;
}

export function pickReason(
  signal: Pick<Signal, "reason" | "reason_ru">,
  lang?: Lang
): string {
  const localized = signal.reason?.trim();
  const raw = localized || signal.reason_ru;
  return lang ? localizeBackendText(raw, lang) : raw;
}

export function pickActionText(
  action: Pick<NextAction, "text" | "text_ru">,
  lang?: Lang
): string {
  const localized = action.text?.trim();
  const raw = localized || action.text_ru;
  return lang ? localizeBackendText(raw, lang) : raw;
}

const CYRILLIC_RE = /[\u0400-\u04FF]/;

export function pickDisclaimer(
  metrics: Pick<
    MetricsResponse,
    "disclaimer" | "disclaimer_ru" | "disclaimer_kk" | "disclaimer_en"
  >,
  lang?: Lang,
  fallback?: string
): string | null {
  const byLang =
    lang === "kk"
      ? metrics.disclaimer_kk?.trim()
      : lang === "en"
        ? metrics.disclaimer_en?.trim()
        : metrics.disclaimer_ru?.trim();

  if (byLang) {
    return lang ? localizeBackendText(byLang, lang) : byLang;
  }

  const generic = metrics.disclaimer?.trim();
  const ruText = metrics.disclaimer_ru?.trim();

  if (generic) {
    if (lang === "en" && CYRILLIC_RE.test(generic)) {
      return fallback?.trim() || null;
    }
    if (lang === "kk" && ruText && generic === ruText) {
      return fallback?.trim() || null;
    }
    return lang ? localizeBackendText(generic, lang) : generic;
  }

  if (lang === "ru" || !lang) {
    if (ruText) {
      return lang ? localizeBackendText(ruText, lang) : ruText;
    }
  }

  return fallback?.trim() || null;
}

export interface VerdictStyle {
  verdict: Verdict;
  badgeClass: string;
  bannerClass: string;
  dotClass: string;
  iconColorClass: string;
  actionButtonClass?: string;
}

export const VERDICT_STYLES: Record<Verdict, VerdictStyle> = {
  green: {
    verdict: "green",
    badgeClass: "border-[#00AB75]/30 bg-[#00AB75]/10 text-[#006B49]",
    bannerClass: "border-[#00AB75]/35 bg-[#E8F8F2] text-[#064A34]",
    dotClass: "bg-[#00AB75]",
    iconColorClass: "text-[var(--brand-text)]",
  },
  yellow: {
    verdict: "yellow",
    badgeClass: "border-amber-300/80 bg-amber-50 text-amber-900",
    bannerClass: "border-amber-300 bg-amber-50/95 text-amber-950",
    dotClass: "bg-amber-500",
    iconColorClass: "text-amber-700",
  },
  red: {
    verdict: "red",
    badgeClass: "border-red-300/80 bg-red-50 text-red-800",
    bannerClass: "border-red-300 bg-red-50/95 text-red-950",
    dotClass: "bg-red-600",
    iconColorClass: "text-red-600",
    actionButtonClass: "bg-red-600 text-white hover:bg-red-700",
  },
  grey: {
    verdict: "grey",
    badgeClass: "border-[#DCDCE2] bg-[#F0F0F5] text-[#4A4A4E]",
    bannerClass: "border-[#DCDCE2] bg-[#F0F0F5] text-[#1D1D1E]",
    dotClass: "bg-[#737376]",
    iconColorClass: "text-[#57575A]",
  },
  invalid: {
    verdict: "invalid",
    badgeClass: "border-rose-300 bg-rose-50 text-rose-950",
    bannerClass: "border-rose-400/80 bg-rose-50/95 text-rose-950",
    dotClass: "bg-rose-900",
    iconColorClass: "text-rose-900",
    actionButtonClass: "bg-rose-900 text-white hover:bg-rose-950",
  },
};
