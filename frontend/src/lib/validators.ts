import { getBankByCode, type BankInfo } from "./banks";

const BIN_WEIGHTS_FIRST = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11] as const;
const BIN_WEIGHTS_SECOND = [3, 4, 5, 6, 7, 8, 9, 10, 11, 1, 2] as const;

const CYRILLIC_RE = /[\u0400-\u052F]/;

export function stripSpacesUpper(value: string): string {
  return value.replace(/\s+/g, "").toUpperCase();
}

export function stripNonDigits(value: string): string {
  return value.replace(/\D+/g, "");
}

/**
 * Formats a KZ IIK in 4-character blocks (e.g. "KZ47 856K ZT50 0410 0100").
 */
export function formatIikGrouped(raw: string): string {
  const clean = stripSpacesUpper(raw);
  if (!clean) return "";
  return clean.replace(/(.{4})(?=.)/g, "$1 ");
}

/**
 * Computes ISO 13616 IBAN mod-97 iteratively without BigInt or float overflow.
 */
export function ibanMod97(iban: string): number {
  const clean = stripSpacesUpper(iban);
  if (clean.length < 5) return -1;
  const rearranged = clean.slice(4) + clean.slice(0, 4);
  let remainder = 0;
  for (let i = 0; i < rearranged.length; i += 1) {
    const code = rearranged.charCodeAt(i);
    if (code >= 48 && code <= 57) {
      remainder = (remainder * 10 + (code - 48)) % 97;
    } else if (code >= 65 && code <= 90) {
      const value = code - 55; // A=10 .. Z=35 (always 2 digits)
      remainder = (remainder * 100 + value) % 97;
    } else {
      return -1;
    }
  }
  return remainder;
}

export type IikValidationCode =
  | "idle"
  | "valid"
  | "incomplete"
  | "cyrillic"
  | "prefix_kz"
  | "alnum"
  | "length"
  | "check_digits"
  | "checksum"
  | "bank_code_digits"
  | "unknown_bank_code";

export interface IikValidationResult {
  status: "idle" | "valid" | "incomplete" | "invalid";
  code: IikValidationCode;
  clean: string;
  length: number;
  bankCode: string | null;
  bank: BankInfo | null;
}

export function validateIikLive(raw: string): IikValidationResult {
  const clean = stripSpacesUpper(raw);
  const length = clean.length;

  if (length === 0) {
    return {
      status: "idle",
      code: "idle",
      clean,
      length,
      bankCode: null,
      bank: null,
    };
  }

  if (CYRILLIC_RE.test(clean)) {
    return {
      status: "invalid",
      code: "cyrillic",
      clean,
      length,
      bankCode: null,
      bank: null,
    };
  }

  if (
    (length >= 1 && clean[0] !== "K") ||
    (length >= 2 && !clean.startsWith("KZ"))
  ) {
    return {
      status: "invalid",
      code: "prefix_kz",
      clean,
      length,
      bankCode: null,
      bank: null,
    };
  }

  if (!/^[A-Z0-9]+$/.test(clean)) {
    return {
      status: "invalid",
      code: "alnum",
      clean,
      length,
      bankCode: null,
      bank: null,
    };
  }

  const rawBankSlice = length >= 7 ? clean.slice(4, 7) : null;
  const hasDigitBankCode = rawBankSlice !== null && /^\d{3}$/.test(rawBankSlice);
  const bankCode = hasDigitBankCode ? rawBankSlice : null;
  const bank = bankCode ? getBankByCode(bankCode) : null;

  if (rawBankSlice !== null && !hasDigitBankCode) {
    return {
      status: "invalid",
      code: "bank_code_digits",
      clean,
      length,
      bankCode: null,
      bank: null,
    };
  }

  if (length < 20) {
    return {
      status: "incomplete",
      code: "incomplete",
      clean,
      length,
      bankCode,
      bank,
    };
  }

  if (length > 20) {
    return {
      status: "invalid",
      code: "length",
      clean,
      length,
      bankCode,
      bank,
    };
  }

  if (!/^\d{2}$/.test(clean.slice(2, 4))) {
    return {
      status: "invalid",
      code: "check_digits",
      clean,
      length,
      bankCode,
      bank,
    };
  }

  if (ibanMod97(clean) !== 1) {
    return {
      status: "invalid",
      code: "checksum",
      clean,
      length,
      bankCode,
      bank,
    };
  }

  if (!bankCode) {
    return {
      status: "invalid",
      code: "bank_code_digits",
      clean,
      length,
      bankCode: null,
      bank: null,
    };
  }

  if (!bank) {
    return {
      status: "invalid",
      code: "unknown_bank_code",
      clean,
      length,
      bankCode,
      bank: null,
    };
  }

  return {
    status: "valid",
    code: "valid",
    clean,
    length,
    bankCode,
    bank,
  };
}

export type BinEntityType =
  | "legal"
  | "ie_joint"
  | "individual_or_ie"
  | "invalid_fifth";

export function getBinEntityType(raw: string): BinEntityType | null {
  const digits = stripNonDigits(raw);
  if (digits.length < 5) return null;
  const fifth = digits[4];
  if (fifth === "4" || fifth === "5") return "legal";
  if (fifth === "6") return "ie_joint";
  if (fifth === "0" || fifth === "1" || fifth === "2" || fifth === "3") {
    return "individual_or_ie";
  }
  return "invalid_fifth";
}

export function computeBinCheckDigit(prefix11: string): number | null {
  if (!/^\d{11}$/.test(prefix11)) return null;
  const digits = Array.from(prefix11, (ch) => Number(ch));

  let sum = 0;
  for (let i = 0; i < 11; i += 1) {
    sum += digits[i] * BIN_WEIGHTS_FIRST[i];
  }
  let remainder = sum % 11;
  if (remainder === 10) {
    sum = 0;
    for (let i = 0; i < 11; i += 1) {
      sum += digits[i] * BIN_WEIGHTS_SECOND[i];
    }
    remainder = sum % 11;
  }
  return remainder === 10 ? null : remainder;
}

export type BinValidationCode =
  | "idle"
  | "valid"
  | "incomplete"
  | "all_zeros"
  | "invalid_month"
  | "invalid_fifth"
  | "checksum";

export interface BinValidationResult {
  status: "idle" | "valid" | "incomplete" | "invalid";
  code: BinValidationCode;
  digits: string;
  length: number;
  entityType: BinEntityType | null;
}

export function validateBinLive(raw: string): BinValidationResult {
  const digits = stripNonDigits(raw);
  const length = digits.length;
  const entityType = getBinEntityType(digits);

  if (length === 0) {
    return {
      status: "idle",
      code: "idle",
      digits,
      length,
      entityType: null,
    };
  }

  if (length >= 4) {
    const month = Number(digits.slice(2, 4));
    if (month < 1 || month > 12) {
      return {
        status: "invalid",
        code: "invalid_month",
        digits,
        length,
        entityType,
      };
    }
  }

  if (entityType === "invalid_fifth") {
    return {
      status: "invalid",
      code: "invalid_fifth",
      digits,
      length,
      entityType,
    };
  }

  if (length < 12) {
    return {
      status: "incomplete",
      code: "incomplete",
      digits,
      length,
      entityType,
    };
  }

  if (digits === "000000000000") {
    return {
      status: "invalid",
      code: "all_zeros",
      digits,
      length,
      entityType,
    };
  }

  const expected = computeBinCheckDigit(digits.slice(0, 11));
  if (expected === null || Number(digits[11]) !== expected) {
    return {
      status: "invalid",
      code: "checksum",
      digits,
      length,
      entityType,
    };
  }

  return {
    status: "valid",
    code: "valid",
    digits,
    length,
    entityType,
  };
}

/**
 * Formats an amount string as the user types:
 * - Inserts spaces as thousands separators
 * - Supports both comma and dot as decimal separators (normalizing to `decimalSep`)
 * - Allows up to 2 fractional digits
 */
export function formatAmountInput(
  raw: string,
  decimalSep: "," | "." = ","
): string {
  const stripped = raw.replace(/[\s\u00A0\u202F₸]+/g, "");
  if (!stripped) return "";

  let intPart = "";
  let fracPart = "";
  let hasDecimal = false;

  for (let i = 0; i < stripped.length; i += 1) {
    const ch = stripped[i];
    if (ch >= "0" && ch <= "9") {
      if (hasDecimal) {
        if (fracPart.length < 2) {
          fracPart += ch;
        }
      } else {
        intPart += ch;
      }
    } else if ((ch === "," || ch === ".") && !hasDecimal) {
      hasDecimal = true;
    }
  }

  if (!intPart && !hasDecimal) {
    return "";
  }

  // Normalize leading zeros (e.g. "0012" -> "12", ",5" -> "0,5")
  const normalizedInt = intPart
    ? intPart.replace(/^0+(?=\d)/, "")
    : "0";

  const groupedInt = normalizedInt.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  return hasDecimal ? `${groupedInt}${decimalSep}${fracPart}` : groupedInt;
}

export function formatNumberToAmountInput(
  value: number | null | undefined,
  decimalSep: "," | "." = ","
): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "";
  }
  const hasFraction = Math.abs(value % 1) > 0.0001;
  const raw = hasFraction ? value.toFixed(2).replace(/0+$/, "") : String(Math.round(value));
  return formatAmountInput(raw, decimalSep);
}

export function parseAmountInput(raw: string): number {
  const cleaned = raw
    .replace(/[\s\u00A0\u202F₸]+/g, "")
    .replace(",", ".")
    .trim();
  if (!cleaned) return Number.NaN;
  return Number(cleaned);
}
