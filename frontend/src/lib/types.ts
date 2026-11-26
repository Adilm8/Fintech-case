export type Verdict = "green" | "yellow" | "red" | "grey" | "invalid";

export type SignalSeverity = "block" | "primary" | "amplifier" | "info";

export type ComparisonField =
  | "name"
  | "bin"
  | "iik"
  | "bik"
  | "bank"
  | "amount";

export type PrimaryAction = "postpone" | "send_to_director" | "sign";

export type ApprovalStatus = "pending" | "approved" | "rejected";

export type ApprovalDecision = "approved" | "rejected";

export type UserRole = "accountant" | "director";

export interface CheckRequest {
  recipient_name: string;
  recipient_bin: string;
  recipient_iik: string;
  recipient_bik: string;
  amount_kzt: number;
  purpose: string;
}

export interface Evidence {
  field: string;
  expected: string | null;
  actual: string | null;
  since: string | null;
}

export interface Signal {
  rule_id: string;
  points: number;
  severity: SignalSeverity;
  reason_ru: string;
  evidence?: Evidence | null;
}

export interface ComparisonRow {
  field: ComparisonField;
  in_invoice: string;
  in_history: string | null;
  last_seen: string | null;
  differs: boolean;
  diff_positions: number[];
}

export interface NextAction {
  text_ru: string;
  primary: PrimaryAction;
  secondary: string[];
}

export interface History {
  payments_count: number;
  last_payment_date: string | null;
  median_amount_kzt: number | null;
}

export interface CheckResult {
  check_id: string;
  verdict: Verdict;
  score: number;
  headline_ru: string;
  signals: Signal[];
  comparison: ComparisonRow[];
  next_action: NextAction;
  history: History;
}

export interface QueueItem {
  id: string;
  request: CheckRequest;
  result: CheckResult;
}

export interface HistoryEntry {
  id?: string;
  recipient_name: string;
  recipient_bin: string;
  recipient_iik: string;
  recipient_bik?: string;
  bank_name?: string;
  amount_kzt: number;
  date?: string;
  purpose?: string;
}

export interface CreateApprovalRequest {
  request: CheckRequest;
  accountant_note: string;
}

export interface Approval {
  id: string;
  request?: CheckRequest;
  check: CheckResult;
  status: ApprovalStatus;
  accountant_note: string;
  director_comment: string | null;
  trust_account: boolean;
  decided_at: string | null;
}

export interface DecisionRequest {
  decision: ApprovalDecision;
  director_comment: string;
  trust_account: boolean;
}
