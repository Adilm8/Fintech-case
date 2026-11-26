import type { Lang } from "@/i18n";
import type { CheckResult } from "./types";

export type ExplainSource = "claude" | "template";

export interface ExplainResponse {
  text: string;
  source: ExplainSource;
  warnings: string[];
}

const API_URL = (
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
).replace(/\/+$/, "");

/**
 * Asks the backend to rephrase an already computed check in plain words.
 * Only the fields the explanation needs are sent (no analyst details).
 */
export async function explainCheck(
  check: CheckResult,
  lang: Lang,
  signal?: AbortSignal,
): Promise<ExplainResponse> {
  const body = {
    lang,
    check: {
      verdict: check.verdict,
      headline: check.headline,
      headline_ru: check.headline_ru,
      signals: check.signals.map((s) => ({
        rule_id: s.rule_id,
        severity: s.severity,
        reason: s.reason,
        reason_ru: s.reason_ru,
      })),
      comparison: check.comparison.map((row) => ({
        field: row.field,
        in_invoice: row.in_invoice,
        in_history: row.in_history,
        differs: row.differs,
      })),
      next_action: {
        text: check.next_action.text,
        text_ru: check.next_action.text_ru,
      },
    },
  };

  const response = await fetch(`${API_URL}/api/explain`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) {
    throw new Error(`Explain request failed with status ${response.status}`);
  }
  const data = (await response.json()) as Partial<ExplainResponse>;
  if (typeof data.text !== "string" || !data.text.trim()) {
    throw new Error("Explain response has no text");
  }
  return {
    text: data.text,
    source: data.source === "claude" ? "claude" : "template",
    warnings: Array.isArray(data.warnings) ? data.warnings : [],
  };
}
