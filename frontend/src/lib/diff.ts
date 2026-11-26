import type { ComparisonRow } from "./types";

export interface CharDiffResult {
  invoicePositions: number[];
  historyPositions: number[];
}

const CYRILLIC_REGEX = /[\u0400-\u04FF]/;
const LATIN_LETTER_REGEX = /^[A-Za-z]$/;

export function hasCyrillic(value: string): boolean {
  return CYRILLIC_REGEX.test(value);
}

export function isLatinLetter(char: string): boolean {
  return LATIN_LETTER_REGEX.test(char);
}

export function isLatinInCyrillic(char: string, fullText: string): boolean {
  return isLatinLetter(char) && hasCyrillic(fullText);
}

function clampValidPositions(positions: number[], length: number): number[] {
  const unique = new Set<number>();
  for (const pos of positions) {
    if (Number.isInteger(pos) && pos >= 0 && pos < length) {
      unique.add(pos);
    }
  }
  return Array.from(unique).sort((a, b) => a - b);
}

export function computeCharDiff(
  invoice: string,
  history: string
): CharDiffResult {
  const a = Array.from(invoice);
  const b = Array.from(history);

  if (a.length === b.length) {
    const diff: number[] = [];
    for (let i = 0; i < a.length; i += 1) {
      if (a[i] !== b[i]) {
        diff.push(i);
      }
    }
    return { invoicePositions: diff, historyPositions: [...diff] };
  }

  let prefix = 0;
  const minLen = Math.min(a.length, b.length);
  while (prefix < minLen && a[prefix] === b[prefix]) {
    prefix += 1;
  }

  let suffix = 0;
  while (
    suffix < minLen - prefix &&
    a[a.length - 1 - suffix] === b[b.length - 1 - suffix]
  ) {
    suffix += 1;
  }

  const aMid = a.slice(prefix, a.length - suffix);
  const bMid = b.slice(prefix, b.length - suffix);
  const m = aMid.length;
  const n = bMid.length;

  if (m === 0 && n === 0) {
    return { invoicePositions: [], historyPositions: [] };
  }

  // Fallback to marking the differing middle range if strings are unusually large
  if (m * n > 40_000) {
    const invoicePositions: number[] = [];
    for (let i = 0; i < m; i += 1) invoicePositions.push(prefix + i);
    const historyPositions: number[] = [];
    for (let j = 0; j < n; j += 1) historyPositions.push(prefix + j);
    return { invoicePositions, historyPositions };
  }

  const dp: Uint16Array[] = Array.from(
    { length: m + 1 },
    () => new Uint16Array(n + 1)
  );

  for (let i = m - 1; i >= 0; i -= 1) {
    for (let j = n - 1; j >= 0; j -= 1) {
      if (aMid[i] === bMid[j]) {
        dp[i][j] = dp[i + 1][j + 1] + 1;
      } else {
        dp[i][j] = Math.max(dp[i + 1][j], dp[i][j + 1]);
      }
    }
  }

  const invoicePositions: number[] = [];
  const historyPositions: number[] = [];
  let i = 0;
  let j = 0;

  while (i < m && j < n) {
    if (aMid[i] === bMid[j]) {
      i += 1;
      j += 1;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      invoicePositions.push(prefix + i);
      i += 1;
    } else {
      historyPositions.push(prefix + j);
      j += 1;
    }
  }

  while (i < m) {
    invoicePositions.push(prefix + i);
    i += 1;
  }

  while (j < n) {
    historyPositions.push(prefix + j);
    j += 1;
  }

  return { invoicePositions, historyPositions };
}

export function resolveComparisonDiff(row: ComparisonRow): CharDiffResult {
  const invoiceChars = Array.from(row.in_invoice ?? "");
  const historyText = row.in_history ?? "";
  const historyChars = Array.from(historyText);

  const backendPositions = Array.isArray(row.diff_positions)
    ? clampValidPositions(row.diff_positions, invoiceChars.length)
    : [];

  if (backendPositions.length > 0) {
    if (!row.in_history) {
      return { invoicePositions: backendPositions, historyPositions: [] };
    }
    if (invoiceChars.length === historyChars.length) {
      return {
        invoicePositions: backendPositions,
        historyPositions: clampValidPositions(
          backendPositions,
          historyChars.length
        ),
      };
    }
    const computed = computeCharDiff(row.in_invoice, historyText);
    return {
      invoicePositions: backendPositions,
      historyPositions: computed.historyPositions,
    };
  }

  if (row.field === "name" && row.differs && row.in_history) {
    return computeCharDiff(row.in_invoice, row.in_history);
  }

  return { invoicePositions: [], historyPositions: [] };
}
