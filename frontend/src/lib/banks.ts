/**
 * Static directory of Kazakhstan banks (IIK bank code -> BIC & name).
 * Copied from backend/data/banks.json (National Bank of Kazakhstan BIC reference).
 */

export interface BankInfo {
  code: string;
  bik: string;
  name: string;
  budget?: boolean;
}

export const KZ_BANKS: readonly BankInfo[] = [
  {
    code: "601",
    bik: "HSBKKZKX",
    name: "АО «Народный Банк Казахстана»",
  },
  {
    code: "722",
    bik: "CASPKZKA",
    name: "АО «Kaspi Bank»",
  },
  {
    code: "965",
    bik: "IRTYKZKA",
    name: "АО «ForteBank»",
  },
  {
    code: "998",
    bik: "TSESKZKA",
    name: "АО «Alatau City Bank»",
  },
  {
    code: "856",
    bik: "KCJBKZKX",
    name: "АО «Банк ЦентрКредит»",
  },
  {
    code: "551",
    bik: "KSNVKZKA",
    name: "АО «Фридом Банк Казахстан»",
  },
  {
    code: "948",
    bik: "EURIKZKA",
    name: "АО «Евразийский Банк»",
  },
  {
    code: "821",
    bik: "KINCKZKA",
    name: "АО «Bank RBK»",
  },
  {
    code: "972",
    bik: "HCSKKZKA",
    name: "АО «Отбасы банк»",
  },
  {
    code: "886",
    bik: "INLMKZKA",
    name: "АО «Home Credit Bank»",
  },
  {
    code: "125",
    bik: "NBRKKZKX",
    name: "РГУ «Национальный Банк Республики Казахстан»",
  },
  {
    code: "949",
    bik: "ATYNKZKA",
    name: "АО «Altyn Bank»",
  },
  {
    code: "913",
    bik: "BKCHKZKA",
    name: "АО ДБ «Банк Китая в Казахстане»",
  },
  {
    code: "914",
    bik: "BRKEKZKA",
    name: "АО «Bereke Bank»",
  },
  {
    code: "832",
    bik: "CITIKZKA",
    name: "АО «Ситибанк Казахстан»",
  },
  {
    code: "907",
    bik: "DVKAKZKA",
    name: "АО «Банк Развития Казахстана»",
  },
  {
    code: "246",
    bik: "HLALKZKZ",
    name: "АО «Исламский Банк ADCB»",
  },
  {
    code: "930",
    bik: "ICBKKZKX",
    name: "АО «Торгово-промышленный Банк Китая в г. Алматы»",
  },
  {
    code: "719",
    bik: "KMFBKZKK",
    name: "АО «KMF Банк»",
  },
  {
    code: "563",
    bik: "KPSTKZKA",
    name: "АО «Казпочта»",
  },
  {
    code: "885",
    bik: "KZIBKZKA",
    name: "АО ДБ «Казахстан-Зираат Интернешнл Банк»",
  },
  {
    code: "724",
    bik: "MOKFKZKA",
    name: "АО «Коммерческий Банк БиЭнКей»",
  },
  {
    code: "849",
    bik: "NURSKZKX",
    name: "АО «Нурбанк»",
  },
  {
    code: "435",
    bik: "SHBKKZKA",
    name: "АО «Шинхан Банк Казахстан»",
  },
  {
    code: "432",
    bik: "VTBAKZKZ",
    name: "ДО АО Банк ВТБ (Казахстан)",
  },
  {
    code: "896",
    bik: "ZAJSKZ22",
    name: "АО «Исламский банк Заман-Банк»",
  },
  {
    code: "070",
    bik: "KKMFKZ2A",
    name: "ГУ «Комитет казначейства Министерства финансов РК»",
    budget: true,
  },
  {
    code: "009",
    bik: "GCVPKZ2A",
    name: "НАО «Государственная корпорация «Правительство для граждан»»",
    budget: true,
  },
] as const;

export const BANK_BY_CODE: Readonly<Record<string, BankInfo>> = Object.freeze(
  Object.fromEntries(KZ_BANKS.map((bank) => [bank.code, bank]))
);

export const BANK_BY_BIK: Readonly<Record<string, BankInfo>> = Object.freeze(
  Object.fromEntries(KZ_BANKS.map((bank) => [bank.bik, bank]))
);

export function getBankByCode(code: string | null | undefined): BankInfo | null {
  if (!code) return null;
  const clean = code.replace(/\s+/g, "");
  return BANK_BY_CODE[clean] ?? null;
}

export function getBankByBik(bik: string | null | undefined): BankInfo | null {
  if (!bik) return null;
  const clean = bik.replace(/\s+/g, "").toUpperCase();
  return BANK_BY_BIK[clean] ?? null;
}

/**
 * Extracts the 3-digit KZ bank code (chars 5–7, 1-based) from an IIK.
 */
export function extractBankCodeFromIik(
  iik: string | null | undefined
): string | null {
  if (!iik) return null;
  const clean = iik.replace(/\s+/g, "").toUpperCase();
  if (clean.length < 7 || !clean.startsWith("KZ")) {
    return null;
  }
  const code = clean.slice(4, 7);
  return /^\d{3}$/.test(code) ? code : null;
}

export function getBankFromIik(
  iik: string | null | undefined
): BankInfo | null {
  const code = extractBankCodeFromIik(iik);
  return code ? getBankByCode(code) : null;
}
