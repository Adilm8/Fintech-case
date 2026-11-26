"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Lang } from "@/i18n";
import { explainCheck, type ExplainResponse } from "@/lib/explain";
import type { CheckResult } from "@/lib/types";

export interface ExplainLabels {
  button: string;
  loading: string;
  error: string;
  templateNote: string;
}

interface ExplainButtonProps {
  check: CheckResult;
  lang: Lang;
  labels: ExplainLabels;
}

type ExplainState =
  | { key: string; status: "loading" }
  | { key: string; status: "error" }
  | { key: string; status: "done"; data: ExplainResponse };

/**
 * Rephrases the already computed check for an accountant. The text is shown in a
 * muted subpanel and never changes the verdict. The result belongs to one
 * check + language pair, so switching either one hides a stale text.
 */
export function ExplainButton({ check, lang, labels }: ExplainButtonProps) {
  const key = `${check.check_id}:${lang}`;
  const [state, setState] = useState<ExplainState | null>(null);

  const current = state && state.key === key ? state : null;
  const loading = current?.status === "loading";

  async function handleClick() {
    const requestKey = key;
    setState({ key: requestKey, status: "loading" });
    try {
      const data = await explainCheck(check, lang);
      // Apply only if no newer request replaced this one in the meantime.
      setState((prev) =>
        prev?.key === requestKey
          ? { key: requestKey, status: "done", data }
          : prev,
      );
    } catch {
      setState((prev) =>
        prev?.key === requestKey ? { key: requestKey, status: "error" } : prev,
      );
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={handleClick}
          disabled={loading}
          aria-busy={loading}
        >
          {loading ? (
            <Loader2 className="animate-spin" aria-hidden="true" />
          ) : null}
          {loading ? labels.loading : labels.button}
        </Button>
      </div>
      <div aria-live="polite">
        {current?.status === "error" ? (
          <p role="alert" className="text-xs font-medium text-[var(--status-danger-text)]">
            {labels.error}
          </p>
        ) : null}
        {current?.status === "done" ? (
          <div className="ui-subpanel space-y-1">
            <p className="text-sm leading-5 text-foreground break-words">
              {current.data.text}
            </p>
            {current.data.source === "template" ? (
              <p className="text-xs text-muted-foreground">
                {labels.templateNote}
              </p>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}
