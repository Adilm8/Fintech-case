import type { Signal } from "./types";

/**
 * Signal rule IDs that cast doubt on the recipient's identity.
 * Must stay in sync with `IDENTITY_SIGNAL_IDS` in `backend/app/risk/config.py`.
 * When any of these signals is present on a yellow or grey check,
 * the accountant's phone-verification checkbox must NOT unlock signing —
 * only director approval can unlock «Подписать».
 */
export const IDENTITY_SIGNAL_IDS = [
  "lookalike_supplier",
  "bin_name_mismatch",
  "entity_type_mismatch",
  "kbe_mismatch",
  "iik_belongs_to_other_counterparty",
  "mixed_script_name",
  "iik_reported_by_clients",
  "fresh_iik_many_payers",
] as const;

export type IdentitySignalId = (typeof IDENTITY_SIGNAL_IDS)[number];

const IDENTITY_SIGNAL_SET: ReadonlySet<string> = new Set(IDENTITY_SIGNAL_IDS);

export function isIdentitySignalId(ruleId: string): ruleId is IdentitySignalId {
  return IDENTITY_SIGNAL_SET.has(ruleId);
}

/**
 * Returns true if any signal in the check result concerns recipient identity.
 */
export function hasIdentitySignal(
  signals: readonly Pick<Signal, "rule_id">[] | null | undefined
): boolean {
  if (!signals || signals.length === 0) return false;
  return signals.some((signal) => IDENTITY_SIGNAL_SET.has(signal.rule_id));
}

/**
 * Returns all signals from a check result that belong to IDENTITY_SIGNAL_IDS.
 */
export function getIdentitySignals<T extends Pick<Signal, "rule_id">>(
  signals: readonly T[] | null | undefined
): T[] {
  if (!signals || signals.length === 0) return [];
  return signals.filter((signal) => IDENTITY_SIGNAL_SET.has(signal.rule_id));
}
