import { getBankByBik, getBankFromIik } from "./banks";
import type { HistoryEntry } from "./types";
import { stripNonDigits, stripSpacesUpper } from "./validators";

export interface SupplierSuggestion {
  bin: string;
  name: string;
  aliases: string[];
  lastIik: string;
  lastBik: string;
  bankName: string | null;
  lastPaidAt: string | null;
  typicalAmountKzt: number | null;
  paymentsCount: number;
  lastPurpose: string | null;
  lastKnp: string | null;
}

function normalizeNameForMatch(value: string): string {
  return value
    .toLowerCase()
    .replace(/[«»"'`„“”]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function computeMedian(numbers: number[]): number | null {
  if (numbers.length === 0) return null;
  const sorted = [...numbers].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 1) {
    return sorted[mid];
  }
  return Math.round(((sorted[mid - 1] + sorted[mid]) / 2) * 100) / 100;
}

/**
 * Groups historical payments by normalized recipient BIN, keeping the most recent
 * verified IIK/BIK, bank name, last payment date, and median (typical) amount.
 */
export function groupHistoryBySupplier(
  entries: HistoryEntry[]
): SupplierSuggestion[] {
  const buckets = new Map<
    string,
    Array<{ entry: HistoryEntry; index: number; dateKey: string }>
  >();

  entries.forEach((entry, index) => {
    const bin = stripNonDigits(entry.recipient_bin || "");
    if (!bin) return;
    const dateKey = (entry.date ?? "").trim();
    const list = buckets.get(bin);
    if (list) {
      list.push({ entry, index, dateKey });
    } else {
      buckets.set(bin, [{ entry, index, dateKey }]);
    }
  });

  const suppliers: SupplierSuggestion[] = [];

  for (const [bin, items] of buckets.entries()) {
    items.sort((a, b) => {
      if (a.dateKey !== b.dateKey) {
        return a.dateKey < b.dateKey ? -1 : 1;
      }
      return a.index - b.index;
    });

    const latest = items[items.length - 1].entry;
    const lastIik = stripSpacesUpper(latest.recipient_iik || "");
    const bankFromIik = getBankFromIik(lastIik);
    const lastBik =
      stripSpacesUpper(latest.recipient_bik || "") || bankFromIik?.bik || "";
    const bankInfo = getBankByBik(lastBik) ?? bankFromIik;

    const aliasSet = new Set<string>();
    const amounts: number[] = [];

    for (const { entry } of items) {
      const trimmedName = entry.recipient_name?.trim();
      if (trimmedName) {
        aliasSet.add(trimmedName);
      }
      if (
        typeof entry.amount_kzt === "number" &&
        Number.isFinite(entry.amount_kzt) &&
        entry.amount_kzt > 0
      ) {
        amounts.push(entry.amount_kzt);
      }
    }

    suppliers.push({
      bin,
      name: latest.recipient_name?.trim() || bin,
      aliases: Array.from(aliasSet),
      lastIik,
      lastBik,
      bankName: latest.bank_name?.trim() || bankInfo?.name || null,
      lastPaidAt: latest.date?.trim() || null,
      typicalAmountKzt: computeMedian(amounts),
      paymentsCount: items.length,
      lastPurpose: latest.purpose?.trim() || null,
      lastKnp: latest.knp?.trim() || null,
    });
  }

  suppliers.sort((a, b) => {
    const dateA = a.lastPaidAt ?? "";
    const dateB = b.lastPaidAt ?? "";
    if (dateA !== dateB) return dateB.localeCompare(dateA);
    if (a.paymentsCount !== b.paymentsCount) {
      return b.paymentsCount - a.paymentsCount;
    }
    return a.name.localeCompare(b.name);
  });

  return suppliers;
}

export function filterSupplierSuggestions(
  suppliers: SupplierSuggestion[],
  rawQuery: string,
  limit = 6
): SupplierSuggestion[] {
  const trimmed = rawQuery.trim();
  if (!trimmed) {
    return suppliers.slice(0, limit);
  }

  const normalizedQuery = normalizeNameForMatch(trimmed);
  const digitsQuery = stripNonDigits(trimmed);

  const scored: Array<{ supplier: SupplierSuggestion; score: number }> = [];

  for (const supplier of suppliers) {
    let score = 0;

    if (digitsQuery.length > 0) {
      if (supplier.bin === digitsQuery) {
        score = Math.max(score, 100);
      } else if (supplier.bin.startsWith(digitsQuery)) {
        score = Math.max(score, 85);
      } else if (supplier.bin.includes(digitsQuery)) {
        score = Math.max(score, 65);
      }
    }

    if (normalizedQuery.length > 0) {
      for (const alias of supplier.aliases) {
        const normAlias = normalizeNameForMatch(alias);
        if (normAlias === normalizedQuery) {
          score = Math.max(score, 95);
        } else if (normAlias.startsWith(normalizedQuery)) {
          score = Math.max(score, 80);
        } else if (normAlias.includes(normalizedQuery)) {
          score = Math.max(score, 60);
        }
      }
    }

    if (score > 0) {
      scored.push({ supplier, score });
    }
  }

  scored.sort((a, b) => {
    if (a.score !== b.score) return b.score - a.score;
    return b.supplier.paymentsCount - a.supplier.paymentsCount;
  });

  return scored.slice(0, limit).map((item) => item.supplier);
}

export function findSupplierByBin(
  suppliers: SupplierSuggestion[],
  rawBin: string | null | undefined
): SupplierSuggestion | null {
  if (!rawBin) return null;
  const digits = stripNonDigits(rawBin);
  if (digits.length !== 12) return null;
  return suppliers.find((s) => s.bin === digits) ?? null;
}

export function findSupplierByName(
  suppliers: SupplierSuggestion[],
  rawName: string | null | undefined
): SupplierSuggestion | null {
  if (!rawName) return null;
  const target = normalizeNameForMatch(rawName);
  if (!target) return null;
  return (
    suppliers.find((s) =>
      s.aliases.some((alias) => normalizeNameForMatch(alias) === target)
    ) ?? null
  );
}
