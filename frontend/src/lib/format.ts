import type { ComparisonField, TrustedInfo, Verdict } from "./types";

export function formatKzt(amount: number | null | undefined): string {
  if (amount === null || amount === undefined || Number.isNaN(amount)) {
    return "—";
  }
  const hasFraction = Math.abs(amount % 1) > 0.001;
  const formatted = new Intl.NumberFormat("ru-RU", {
    minimumFractionDigits: hasFraction ? 2 : 0,
    maximumFractionDigits: hasFraction ? 2 : 0,
  })
    .format(amount)
    .replace(/\u00a0/g, " ");

  return `${formatted} ₸`;
}

export function formatDateRu(dateStr: string | null | undefined): string {
  if (!dateStr) return "—";
  const parsed = new Date(dateStr);
  if (Number.isNaN(parsed.getTime())) {
    return dateStr;
  }
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(parsed);
}

export function formatTrustedBannerText(
  trustedInfo: TrustedInfo | null | undefined
): string {
  const datePart = trustedInfo?.decided_at
    ? ` ${formatDateRu(trustedInfo.decided_at)}`
    : "";
  const comment = trustedInfo?.director_comment?.trim();
  const base = `Новый счёт подтверждён директором${datePart}`;
  return comment ? `${base}: ${comment}` : base;
}

export interface VerdictMeta {
  verdict: Verdict;
  labelRu: string;
  badgeClass: string;
  bannerClass: string;
  dotClass: string;
  iconColorClass: string;
}

export const VERDICT_META: Record<Verdict, VerdictMeta> = {
  green: {
    verdict: "green",
    labelRu: "Всё как раньше",
    badgeClass: "border-emerald-200 bg-emerald-50 text-emerald-800",
    bannerClass: "border-emerald-200 bg-emerald-50/90 text-emerald-950",
    dotClass: "bg-emerald-600",
    iconColorClass: "text-emerald-600",
  },
  yellow: {
    verdict: "yellow",
    labelRu: "Есть изменения",
    badgeClass: "border-amber-200 bg-amber-50 text-amber-900",
    bannerClass: "border-amber-200 bg-amber-50/90 text-amber-950",
    dotClass: "bg-amber-500",
    iconColorClass: "text-amber-600",
  },
  red: {
    verdict: "red",
    labelRu: "Похоже на подмену",
    badgeClass: "border-red-200 bg-red-50 text-red-800",
    bannerClass: "border-red-300 bg-red-50/90 text-red-950",
    dotClass: "bg-red-600",
    iconColorClass: "text-red-600",
  },
  grey: {
    verdict: "grey",
    labelRu: "Нет истории",
    badgeClass: "border-slate-200 bg-slate-100 text-slate-700",
    bannerClass: "border-slate-200 bg-slate-100/90 text-slate-900",
    dotClass: "bg-slate-500",
    iconColorClass: "text-slate-600",
  },
  invalid: {
    verdict: "invalid",
    labelRu: "Ошибка в реквизитах",
    badgeClass: "border-orange-300 bg-orange-50 text-orange-900",
    bannerClass: "border-orange-300 bg-orange-50/90 text-orange-950",
    dotClass: "bg-orange-600",
    iconColorClass: "text-orange-600",
  },
};

export const FIELD_LABELS: Record<ComparisonField, string> = {
  name: "Наименование получателя",
  bin: "БИН / ИИН",
  iik: "ИИК (счёт)",
  bik: "БИК",
  bank: "Банк получателя",
  amount: "Сумма платежа",
};

export const SIGNAL_RULE_LABELS: Record<string, string> = {
  trusted_account: "Доверенный счёт (подтверждён директором)",
  iik_changed: "Изменён ИИК получателя",
  bank_changed: "Изменён банк получателя",
  bik_changed: "Изменён БИК банка",
  bin_changed: "Изменён БИН / ИИН",
  name_lookalike: "Похожее наименование поставщика",
  homoglyph_name: "Символы другого алфавита в названии",
  bcc_account_mismatch: "Владелец счёта в BCC не совпадает",
  amount_anomaly: "Нетипичная сумма платежа",
  urgent_purpose: "Признаки срочности в назначении",
  first_payment: "Первый платёж получателю",
};
