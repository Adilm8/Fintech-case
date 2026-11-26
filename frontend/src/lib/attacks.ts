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

const LEGAL_FORM_TOKENS = new Set([
  "ТОО",
  "АО",
  "ЖШС",
  "АҚ",
  "АК",
  "ИП",
  "ЖК",
  "КХ",
  "ПК",
  "ОАО",
  "ЗАО",
  "ООО",
  "ГКП",
  "РГП",
  "LLP",
  "JSC",
  "TOO",
  "AO",
  "IP",
  "IE",
]);

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

const URGENT_KEYWORD_RU = "\u0441\u0440\u043e\u0447\u043d\u043e"; // "срочно"
export const INVISIBLE_CGJ = "\u034F"; // COMBINING GRAPHEME JOINER

const BIN_WEIGHTS_1 = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11] as const;
const BIN_WEIGHTS_2 = [3, 4, 5, 6, 7, 8, 9, 10, 11, 1, 2] as const;

/**
 * Computes a valid 12-digit KZ BIN/IIN from an 11-digit prefix using official mod-11 weights.
 */
export function buildValidKzBin(prefix11: string): string {
  const digits = prefix11.replace(/\D+/g, "").slice(0, 11).split("").map(Number);
  if (digits.length !== 11) {
    throw new Error("BIN prefix must contain 11 digits");
  }
  let rem =
    digits.reduce((acc, d, idx) => acc + d * BIN_WEIGHTS_1[idx], 0) % 11;
  if (rem === 10) {
    rem = digits.reduce((acc, d, idx) => acc + d * BIN_WEIGHTS_2[idx], 0) % 11;
  }
  if (rem === 10) {
    // Bump last digit of prefix by 1 and recompute if double-10 edge case ever occurs.
    const nextPrefix = `${prefix11.slice(0, 10)}${(digits[10] + 1) % 10}`;
    return buildValidKzBin(nextPrefix);
  }
  return `${digits.join("")}${rem}`;
}

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

interface NameWordSpan {
  word: string;
  start: number;
  end: number;
  isLegalForm: boolean;
}

function tokenizeRecipientName(name: string): NameWordSpan[] {
  const spans: NameWordSpan[] = [];
  const regex = /[\p{L}\p{N}]+/gu;
  let match: RegExpExecArray | null;
  while ((match = regex.exec(name)) !== null) {
    const word = match[0];
    const upper = word.toUpperCase();
    spans.push({
      word,
      start: match.index,
      end: match.index + word.length,
      isLegalForm: LEGAL_FORM_TOKENS.has(upper),
    });
  }
  return spans;
}

/**
 * Replaces a Cyrillic letter in the distinctive part of recipient_name (skipping legal forms
 * such as ТОО, АО, ИП, ЖШС) with a visually identical Latin homoglyph.
 */
export function applyHomoglyphAttack(request: CheckRequest): CheckRequest {
  const name = request.recipient_name;
  const spans = tokenizeRecipientName(name);
  const distinctiveSpans = spans.filter((span) => !span.isLegalForm);

  // Prefer uppercase distinctive letters (e.g. "С" in "Снаб") or consonant homoglyphs in later
  // distinctive tokens first, then any replaceable letter in distinctive tokens.
  const searchOrder: NameWordSpan[] =
    distinctiveSpans.length > 1
      ? [...distinctiveSpans.slice(1), distinctiveSpans[0]]
      : distinctiveSpans;

  for (const span of searchOrder) {
    for (let i = span.start; i < span.end; i += 1) {
      const ch = name[i];
      const replacement = CYRILLIC_TO_LATIN_MAP[ch];
      if (replacement) {
        return {
          ...request,
          recipient_name: `${name.slice(0, i)}${replacement}${name.slice(i + 1)}`,
        };
      }
    }
  }

  return request;
}

/**
 * Inserts an invisible Unicode Combining Grapheme Joiner (U+034F) inside a distinctive word
 * of recipient_name while leaving the visible text unchanged.
 */
export function applyInvisibleCharAttack(request: CheckRequest): CheckRequest {
  const name = request.recipient_name;
  if (name.includes(INVISIBLE_CGJ)) {
    return request;
  }

  const spans = tokenizeRecipientName(name);
  const targetSpan =
    spans.find((span) => !span.isLegalForm && span.word.length >= 2) ??
    spans.find((span) => !span.isLegalForm) ??
    spans[0];

  if (!targetSpan) {
    return {
      ...request,
      recipient_name: `${name}${INVISIBLE_CGJ}`,
    };
  }

  const insertAt =
    targetSpan.word.length >= 2 ? targetSpan.start + 1 : targetSpan.end;
  return {
    ...request,
    recipient_name: `${name.slice(0, insertAt)}${INVISIBLE_CGJ}${name.slice(insertAt)}`,
  };
}

/**
 * Swaps the 3-digit bank code in a KZ IIK to a different bank, recomputes a valid
 * ISO-7064 mod-97 checksum, and updates the BIC to match so pre-validation passes.
 * Leaves recipient_bin unchanged (BEC account-change case).
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
 * Replaces both BIN and IIK/BIK with an attacker's own valid credentials (mod-11 BIN +
 * matching mod-97 IIK & BIK) while keeping the exact supplier recipient_name.
 */
export function applyOwnBinOwnAccountAttack(
  request: CheckRequest
): CheckRequest {
  const cleanBin = request.recipient_bin.replace(/\s+/g, "");
  const cleanIik = request.recipient_iik.replace(/\s+/g, "").toUpperCase();
  const currentBankCode =
    cleanIik.length >= 7 && cleanIik.startsWith("KZ")
      ? cleanIik.slice(4, 7)
      : "";

  const candidateBins = [
    buildValidKzBin("26014007788"),
    buildValidKzBin("26024009911"),
  ];
  const attackerBin =
    candidateBins.find((bin) => bin !== cleanBin) ?? candidateBins[0];

  const attackerBank =
    OTHER_KZ_BANKS.find((bank) => bank.code !== currentBankCode) ??
    OTHER_KZ_BANKS[0];
  const attackerIik = buildValidKzIik(attackerBank.code, "0008844112233");

  return {
    ...request,
    recipient_bin: attackerBin,
    recipient_iik: attackerIik,
    recipient_bik: attackerBank.bik,
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
 * Appends the Russian urgency keyword ("срочно") recognized by the backend rules
 * regardless of the active UI language.
 */
export function applyUrgentPurposeAttack(request: CheckRequest): CheckRequest {
  const trimmed = request.purpose.trim();
  if (trimmed.toLowerCase().includes(URGENT_KEYWORD_RU)) {
    return request;
  }
  return {
    ...request,
    purpose: trimmed ? `${trimmed}, ${URGENT_KEYWORD_RU}` : URGENT_KEYWORD_RU,
  };
}
