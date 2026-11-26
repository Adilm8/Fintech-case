import type { Lang } from "@/i18n";
import type { CheckRequest } from "./types";

/**
 * Visually identical Cyrillic-to-Latin homoglyph substitution table.
 */
export const CYRILLIC_TO_LATIN_MAP: Record<string, string> = {
  "\u0410": "A", // А -> A
  "\u0412": "B", // В -> B
  "\u0415": "E", // Е -> E
  "\u041A": "K", // К -> K
  "\u041C": "M", // М -> M
  "\u041D": "H", // Н -> H
  "\u041E": "O", // О -> O
  "\u0420": "P", // Р -> P
  "\u0421": "C", // С -> C
  "\u0422": "T", // Т -> T
  "\u0425": "X", // Х -> X
  "\u0430": "a", // а -> a
  "\u0435": "e", // е -> e
  "\u043E": "o", // о -> o
  "\u0440": "p", // р -> p
  "\u0441": "c", // с -> c
  "\u0445": "x", // х -> x
};

const OTHER_KZ_BANKS: readonly { code: string; bik: string }[] = [
  { code: "722", bik: "CASPKZKA" }, // Kaspi Bank
  { code: "965", bik: "IRTYKZKA" }, // ForteBank
  { code: "601", bik: "HSBKKZKX" }, // Halyk Bank
  { code: "948", bik: "EURIKZKA" }, // Eurasian Bank
  { code: "551", bik: "KSNVKZKA" }, // Freedom Bank
  { code: "914", bik: "BRKEKZKA" }, // Bereke Bank
];

const BCC_BANK_CODE = "856";
const BCC_BIK = "KCJBKZKX";

/**
 * Valid BCC accounts belonging to other companies in the demo registry.
 * Using a registered foreign-owned BCC IIK with matching BCC BIC triggers
 * the blocking account-holder mismatch check while passing IBAN/BIC validation.
 */
const BCC_OTHER_COMPANY_ACCOUNTS: readonly {
  iik: string;
  ownerBin: string;
}[] = [
  { iik: "KZ51856KZT2486117574", ownerBin: "251143299639" },
  { iik: "KZ19856KZT5265202294", ownerBin: "260242134665" },
  { iik: "KZ65856KZT0724453180", ownerBin: "251247446379" },
];

const URGENT_SUFFIX_BY_LANG: Record<Lang, string> = {
  ru: "\u0441\u0440\u043e\u0447\u043d\u043e",
  kk: "\u0448\u04b1\u0493\u044b\u043b",
  en: "urgent",
};

function mod97NumericString(alphanumeric: string): number {
  let remainder = 0;
  for (const ch of alphanumeric.toUpperCase()) {
    const code = ch.charCodeAt(0);
    if (code >= 48 && code <= 57) {
      remainder = (remainder * 10 + (code - 48)) % 97;
    } else if (code >= 65 && code <= 90) {
      const value = code - 55; // A=10 .. Z=35
      remainder = (remainder * 100 + value) % 97;
    }
  }
  return remainder;
}

/**
 * Builds a valid 20-character Kazakhstan IBAN (IIK) with ISO-7064 mod-97 check digits:
 * KZ + <2 check digits> + <3-digit bank code> + <13-char account suffix>.
 */
export function buildValidKzIik(bankCode: string, accountSuffix: string): string {
  const cleanBank = bankCode.replace(/\D+/g, "").padStart(3, "0").slice(0, 3);
  const cleanSuffix = accountSuffix
    .replace(/[^A-Za-z0-9]/g, "")
    .toUpperCase()
    .padEnd(13, "0")
    .slice(0, 13);
  const bban = `${cleanBank}${cleanSuffix}`;
  const remainder = mod97NumericString(`${bban}KZ00`);
  const checkDigits = String(98 - remainder).padStart(2, "0");
  return `KZ${checkDigits}${bban}`;
}

/**
 * Replaces the first replaceable Cyrillic letter in recipient_name with a visually
 * identical Latin character.
 */
export function applyHomoglyphAttack(request: CheckRequest): CheckRequest {
  const chars = Array.from(request.recipient_name);
  for (let i = 0; i < chars.length; i += 1) {
    const replacement = CYRILLIC_TO_LATIN_MAP[chars[i]];
    if (replacement) {
      chars[i] = replacement;
      return {
        ...request,
        recipient_name: chars.join(""),
      };
    }
  }
  return request;
}

/**
 * Swaps the 3-digit bank code in a KZ IIK to a different bank, recomputes a valid
 * ISO-7064 mod-97 checksum, and updates the BIC to match so pre-validation passes.
 */
export function applyOtherBankIikAttack(request: CheckRequest): CheckRequest {
  const cleanIik = request.recipient_iik.replace(/\s+/g, "").toUpperCase();
  const currentBankCode =
    cleanIik.length >= 7 && cleanIik.startsWith("KZ")
      ? cleanIik.slice(4, 7)
      : "";
  const accountSuffix =
    cleanIik.length >= 20 && cleanIik.startsWith("KZ")
      ? cleanIik.slice(7, 20)
      : "0005016525808";

  const currentIdx = OTHER_KZ_BANKS.findIndex(
    (bank) => bank.code === currentBankCode
  );
  const nextBank =
    currentIdx >= 0
      ? OTHER_KZ_BANKS[(currentIdx + 1) % OTHER_KZ_BANKS.length]
      : OTHER_KZ_BANKS[0];

  return {
    ...request,
    recipient_iik: buildValidKzIik(nextBank.code, accountSuffix),
    recipient_bik: nextBank.bik,
  };
}

/**
 * Substitutes a valid BCC-bank IIK owned by a different company (and sets BCC BIC).
 */
export function applyBccOtherCompanyAttack(request: CheckRequest): CheckRequest {
  const cleanBin = request.recipient_bin.replace(/\s+/g, "");
  const cleanIik = request.recipient_iik.replace(/\s+/g, "").toUpperCase();

  const candidate =
    BCC_OTHER_COMPANY_ACCOUNTS.find(
      (acc) => acc.ownerBin !== cleanBin && acc.iik !== cleanIik
    ) ??
    BCC_OTHER_COMPANY_ACCOUNTS.find((acc) => acc.ownerBin !== cleanBin) ??
    {
      iik: buildValidKzIik(BCC_BANK_CODE, "KZT9911223344"),
      ownerBin: "",
    };

  return {
    ...request,
    recipient_iik: candidate.iik,
    recipient_bik: BCC_BIK,
  };
}

/**
 * Multiplies the payment amount by the given factor (default x4).
 */
export function applyMultiplyAmountAttack(
  request: CheckRequest,
  factor = 4
): CheckRequest {
  const base =
    Number.isFinite(request.amount_kzt) && request.amount_kzt > 0
      ? request.amount_kzt
      : 1_000_000;
  const nextAmount = Math.round(base * factor * 100) / 100;
  return {
    ...request,
    amount_kzt: nextAmount,
  };
}

/**
 * Appends a localized urgency keyword to the payment purpose.
 */
export function applyUrgentPurposeAttack(
  request: CheckRequest,
  lang: Lang = "ru"
): CheckRequest {
  const keyword = URGENT_SUFFIX_BY_LANG[lang] ?? URGENT_SUFFIX_BY_LANG.ru;
  const trimmed = request.purpose.trim();
  if (trimmed.toLowerCase().includes(keyword.toLowerCase())) {
    return request;
  }
  return {
    ...request,
    purpose: trimmed ? `${trimmed} ${keyword}` : keyword,
  };
}
