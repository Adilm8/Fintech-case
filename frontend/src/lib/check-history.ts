import type {
  Approval,
  AuditEntry,
  CheckRequest,
  CheckResult,
  QueueItem,
  Verdict,
} from "./types";

export interface SessionCheckRecord {
  check_id: string;
  timestamp: string;
  request: CheckRequest;
  result: CheckResult;
  action: string;
}

export interface MergedCheckHistoryRow {
  check_id: string;
  timestamp: string;
  verdict: Verdict;
  score: number | null;
  signal_ids: string[];
  action: string;
  actions: string[];
  source: "both" | "session" | "audit";
  recipient_name: string | null;
  recipient_bin: string | null;
  recipient_iik: string | null;
  recipient_bik: string | null;
  amount_kzt: number | null;
  purpose: string | null;
  request_sha256: string | null;
  ruleset_version: string | null;
  approval_id: string | null;
  queue_item_id: string | null;
  headline: string | null;
  headline_ru: string | null;
}

const SESSION_CHECKS_KEY = "business-shield.session-checks";
const MAX_SESSION_CHECKS = 200;

const EMPTY_SESSION_CHECKS: SessionCheckRecord[] = [];

let cachedSessionChecks: SessionCheckRecord[] | null = null;
const listeners = new Set<() => void>();

function isValidSessionCheck(value: unknown): value is SessionCheckRecord {
  if (!value || typeof value !== "object") return false;
  const rec = value as Partial<SessionCheckRecord>;
  return (
    typeof rec.check_id === "string" &&
    typeof rec.timestamp === "string" &&
    Boolean(rec.request) &&
    typeof rec.request === "object" &&
    Boolean(rec.result) &&
    typeof rec.result === "object"
  );
}

function readSessionChecks(): SessionCheckRecord[] {
  if (typeof window === "undefined") {
    return EMPTY_SESSION_CHECKS;
  }
  try {
    const raw = window.sessionStorage.getItem(SESSION_CHECKS_KEY);
    if (!raw) return EMPTY_SESSION_CHECKS;
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return EMPTY_SESSION_CHECKS;
    const valid = parsed.filter(isValidSessionCheck);
    return valid.length > 0 ? valid : EMPTY_SESSION_CHECKS;
  } catch {
    return EMPTY_SESSION_CHECKS;
  }
}

function writeSessionChecks(records: SessionCheckRecord[]): void {
  if (typeof window === "undefined") return;
  try {
    if (records.length === 0) {
      window.sessionStorage.removeItem(SESSION_CHECKS_KEY);
    } else {
      window.sessionStorage.setItem(
        SESSION_CHECKS_KEY,
        JSON.stringify(records.slice(0, MAX_SESSION_CHECKS))
      );
    }
  } catch {
    // Ignore storage write errors in restricted browsing contexts.
  }
}

export function getSessionChecksSnapshot(): SessionCheckRecord[] {
  if (typeof window === "undefined") {
    return EMPTY_SESSION_CHECKS;
  }
  if (cachedSessionChecks === null) {
    cachedSessionChecks = readSessionChecks();
  }
  return cachedSessionChecks;
}

export function getServerSessionChecksSnapshot(): SessionCheckRecord[] {
  return EMPTY_SESSION_CHECKS;
}

export function subscribeSessionChecks(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function recordSessionCheck(
  request: CheckRequest,
  result: CheckResult,
  action = "check"
): void {
  if (typeof window === "undefined") return;
  const entry: SessionCheckRecord = {
    check_id: result.check_id,
    timestamp: new Date().toISOString(),
    request,
    result,
    action,
  };
  const prev = getSessionChecksSnapshot();
  const next = [
    entry,
    ...prev.filter((item) => item.check_id !== result.check_id),
  ].slice(0, MAX_SESSION_CHECKS);
  cachedSessionChecks = next;
  writeSessionChecks(next);
  listeners.forEach((cb) => cb());
}

export function clearSessionChecks(): void {
  cachedSessionChecks = EMPTY_SESSION_CHECKS;
  writeSessionChecks(EMPTY_SESSION_CHECKS);
  listeners.forEach((cb) => cb());
}

function parseTimestampMs(ts: string): number {
  const ms = Date.parse(ts);
  return Number.isFinite(ms) ? ms : 0;
}

/**
 * Merges client-side session checks with server audit entries by `check_id`,
 * enriching with queue/approval context when available.
 */
export function mergeCheckHistory(
  sessionChecks: readonly SessionCheckRecord[],
  auditEntries: readonly AuditEntry[],
  queueItems: readonly QueueItem[],
  approvals: readonly Approval[]
): MergedCheckHistoryRow[] {
  const queueByCheckId = new Map<string, QueueItem>();
  for (const item of queueItems) {
    queueByCheckId.set(item.result.check_id, item);
  }

  const approvalByCheckId = new Map<string, Approval>();
  for (const approval of approvals) {
    approvalByCheckId.set(approval.check.check_id, approval);
  }

  const map = new Map<string, MergedCheckHistoryRow>();

  for (const audit of auditEntries) {
    const existing = map.get(audit.check_id);
    const matchedQueue = queueByCheckId.get(audit.check_id);
    const matchedApproval = approvalByCheckId.get(audit.check_id);
    const req = matchedQueue?.request ?? matchedApproval?.request ?? null;
    const res = matchedQueue?.result ?? matchedApproval?.check ?? null;

    if (!existing) {
      map.set(audit.check_id, {
        check_id: audit.check_id,
        timestamp: audit.timestamp,
        verdict: audit.verdict,
        score: res?.score ?? null,
        signal_ids: Array.from(new Set(audit.signal_ids ?? [])),
        action: audit.action,
        actions: audit.action ? [audit.action] : [],
        source: "audit",
        recipient_name: req?.recipient_name ?? null,
        recipient_bin: req?.recipient_bin ?? null,
        recipient_iik: req?.recipient_iik ?? null,
        recipient_bik: req?.recipient_bik ?? null,
        amount_kzt: req?.amount_kzt ?? null,
        purpose: req?.purpose ?? null,
        request_sha256: audit.request_sha256 || null,
        ruleset_version: audit.ruleset_version ?? res?.ruleset_version ?? null,
        approval_id: audit.approval_id ?? matchedApproval?.id ?? null,
        queue_item_id: matchedQueue?.id ?? null,
        headline: res?.headline ?? null,
        headline_ru: res?.headline_ru ?? null,
      });
    } else {
      const mergedActions = existing.actions.includes(audit.action)
        ? existing.actions
        : [...existing.actions, audit.action];
      const mergedSignals = Array.from(
        new Set([...existing.signal_ids, ...(audit.signal_ids ?? [])])
      );
      const isNewer =
        parseTimestampMs(audit.timestamp) >=
        parseTimestampMs(existing.timestamp);
      map.set(audit.check_id, {
        ...existing,
        timestamp: isNewer ? audit.timestamp : existing.timestamp,
        verdict: isNewer ? audit.verdict : existing.verdict,
        action: isNewer ? audit.action : existing.action,
        actions: mergedActions,
        signal_ids: mergedSignals,
        approval_id: audit.approval_id ?? existing.approval_id,
        request_sha256: audit.request_sha256 || existing.request_sha256,
        ruleset_version: audit.ruleset_version ?? existing.ruleset_version,
      });
    }
  }

  for (const session of sessionChecks) {
    const existing = map.get(session.check_id);
    const matchedQueue = queueByCheckId.get(session.check_id);
    const sessionSignals = session.result.signals.map((s) => s.rule_id);

    if (!existing) {
      map.set(session.check_id, {
        check_id: session.check_id,
        timestamp: session.timestamp,
        verdict: session.result.verdict,
        score: session.result.score,
        signal_ids: Array.from(new Set(sessionSignals)),
        action: session.action,
        actions: session.action ? [session.action] : [],
        source: "session",
        recipient_name: session.request.recipient_name,
        recipient_bin: session.request.recipient_bin,
        recipient_iik: session.request.recipient_iik,
        recipient_bik: session.request.recipient_bik,
        amount_kzt: session.request.amount_kzt,
        purpose: session.request.purpose,
        request_sha256: null,
        ruleset_version: session.result.ruleset_version ?? null,
        approval_id: null,
        queue_item_id: matchedQueue?.id ?? null,
        headline: session.result.headline ?? null,
        headline_ru: session.result.headline_ru ?? null,
      });
    } else {
      const mergedActions = existing.actions.includes(session.action)
        ? existing.actions
        : [session.action, ...existing.actions];
      const mergedSignals = Array.from(
        new Set([...sessionSignals, ...existing.signal_ids])
      );
      map.set(session.check_id, {
        ...existing,
        source: "both",
        score: session.result.score,
        signal_ids: mergedSignals,
        actions: mergedActions,
        recipient_name: session.request.recipient_name,
        recipient_bin: session.request.recipient_bin,
        recipient_iik: session.request.recipient_iik,
        recipient_bik: session.request.recipient_bik,
        amount_kzt: session.request.amount_kzt,
        purpose: session.request.purpose,
        ruleset_version:
          existing.ruleset_version ?? session.result.ruleset_version ?? null,
        queue_item_id: existing.queue_item_id ?? matchedQueue?.id ?? null,
        headline: session.result.headline ?? existing.headline,
        headline_ru: session.result.headline_ru ?? existing.headline_ru,
      });
    }
  }

  return Array.from(map.values()).sort(
    (a, b) => parseTimestampMs(b.timestamp) - parseTimestampMs(a.timestamp)
  );
}

/**
 * Neutralizes spreadsheet formula injection and escapes RFC 4180 CSV cells.
 */
function escapeCsvCell(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "";
  let str = String(value);
  if (/^[=+\-@\t\r]/.test(str)) {
    str = `'${str}`;
  }
  if (/[",\r\n]/.test(str)) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

export function buildCheckHistoryCsv(
  rows: readonly MergedCheckHistoryRow[],
  resolveActionLabel: (action: string) => string,
  resolveVerdictLabel: (verdict: Verdict) => string,
  resolveSignalLabel: (ruleId: string) => string
): string {
  const headers = [
    "timestamp",
    "check_id",
    "action",
    "verdict",
    "score",
    "recipient_name",
    "recipient_bin",
    "recipient_iik",
    "recipient_bik",
    "amount_kzt",
    "signals",
    "source",
    "request_sha256",
  ];

  const lines = [headers.join(",")];
  for (const row of rows) {
    const signalsText = row.signal_ids
      .map((id) => `${id} (${resolveSignalLabel(id)})`)
      .join("; ");
    const values = [
      row.timestamp,
      row.check_id,
      row.actions.map(resolveActionLabel).join("; "),
      resolveVerdictLabel(row.verdict),
      row.score ?? "",
      row.recipient_name ?? "",
      row.recipient_bin ?? "",
      row.recipient_iik ?? "",
      row.recipient_bik ?? "",
      row.amount_kzt ?? "",
      signalsText,
      row.source,
      row.request_sha256 ?? "",
    ];
    lines.push(values.map(escapeCsvCell).join(","));
  }

  // UTF-8 BOM for clean Excel Cyrillic/Kazakh display on Windows
  return `\uFEFF${lines.join("\r\n")}\r\n`;
}

export function downloadCsvFile(csvContent: string, filename: string): void {
  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
