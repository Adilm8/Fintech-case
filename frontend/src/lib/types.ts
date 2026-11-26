export type Verdict = "green" | "yellow" | "red" | "grey" | "invalid";

export type SignalSeverity = "block" | "primary" | "amplifier" | "info";

export type ComparisonField =
  | "name"
  | "bin"
  | "iik"
  | "bik"
  | "bank"
  | "amount"
  | "kbe"
  | "knp";

export type PrimaryAction = "postpone" | "send_to_director" | "sign";

export type ApprovalStatus = "pending" | "approved" | "rejected";

export type ApprovalDecision = "approved" | "rejected";

export interface CheckRequest {
  payer_id?: string;
  recipient_name: string;
  recipient_bin: string;
  recipient_iik: string;
  recipient_bik: string;
  amount_kzt: number;
  purpose: string;
  kbe?: string;
  knp?: string;
}

export interface SignPaymentPayload {
  check_id: string;
  verdict: Verdict;
  request: CheckRequest;
  accountant_ack: boolean;
  approval_id?: string | null;
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
  reason?: string;
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
  text?: string;
  text_ru: string;
  primary: PrimaryAction;
  secondary: string[];
}

export interface History {
  payments_count: number;
  last_payment_date: string | null;
  median_amount_kzt: number | null;
  compared_with?: string | null;
}

export interface TrustedInfo {
  decided_at: string | null;
  director_comment: string | null;
}

export interface AnalystSignalDetail {
  rule_id: string;
  reason?: string;
  reason_ru: string;
  evidence?: Evidence | null;
}

export interface BccAccountAnalystInfo {
  iik: string;
  owner_bin: string;
  owner_name: string;
  opened_at: string;
  age_days: number;
  owner_matches_recipient: boolean;
}

export interface AnalystDetails {
  bcc_account?: BccAccountAnalystInfo | null;
  signal_details?: AnalystSignalDetail[];
}

export interface CheckResult {
  check_id: string;
  verdict: Verdict;
  score: number;
  headline?: string;
  headline_ru: string;
  signals: Signal[];
  comparison: ComparisonRow[];
  next_action: NextAction;
  history: History;
  trusted?: boolean;
  trusted_info?: TrustedInfo | null;
  analyst_details?: AnalystDetails | null;
  ruleset_version?: string | null;
}

export interface QueueItem {
  id: string;
  request: CheckRequest;
  result: CheckResult;
}

export interface HistoryEntry {
  id?: string;
  payer_id?: string;
  recipient_name: string;
  recipient_bin: string;
  recipient_iik: string;
  recipient_bik?: string;
  bank_name?: string;
  amount_kzt: number;
  date?: string;
  paid_at?: string;
  purpose?: string;
  knp?: string;
}

export interface AuditEntry {
  timestamp: string;
  check_id: string;
  request_sha256: string;
  ruleset_version?: string;
  verdict: Verdict;
  signal_ids: string[];
  action: string;
  approval_id?: string | null;
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
  created_at?: string | null;
}

export interface DecisionRequest {
  decision: ApprovalDecision;
  director_comment: string;
  trust_account: boolean;
}

export interface MetricsVerdictCounts {
  green?: number;
  yellow?: number;
  red?: number;
  grey?: number;
  invalid?: number;
}

export interface MetricsConfusion {
  tp?: number;
  fn?: number;
  fp?: number;
  tn?: number;
}

export interface MetricsSummary {
  total_cases?: number;
  total_legit?: number;
  total_attack?: number;
  detection_rate?: number;
  false_positive_rate?: number;
  precision?: number;
  f1?: number;
  accuracy?: number;
}

export interface MetricsKindItem {
  kind?: string;
  label?: string;
  label_ru?: string;
  label_kk?: string;
  label_en?: string;
  title?: string;
  title_ru?: string;
  title_kk?: string;
  title_en?: string;
  name?: string;
  name_ru?: string;
  name_kk?: string;
  name_en?: string;
  description?: string;
  description_ru?: string;
  description_kk?: string;
  description_en?: string;
  category?: string;
  count?: number;
  total?: number;
  detected?: number;
  flagged_count?: number;
  rate?: number | null;
  detection_rate?: number | null;
  false_positive_rate?: number | null;
  verdicts?: MetricsVerdictCounts;
}

export interface HistoryReplayMetrics {
  total_payments?: number;
  total?: number;
  payments_count?: number;
  count?: number;
  alert_rate?: number | null;
  false_positive_rate?: number | null;
  flagged_count?: number;
  alert_count?: number;
  alerts?: number;
  verdicts?: MetricsVerdictCounts;
  period_days?: number;
  period?: string;
}

export interface MetricsResponse {
  seed?: number;
  dataset_path?: string;
  ruleset_version?: string | null;
  positive_verdicts?: Verdict[];
  summary?: MetricsSummary;
  confusion?: MetricsConfusion;
  verdict_by_label?: Record<string, MetricsVerdictCounts>;
  history_replay?: HistoryReplayMetrics | null;
  total?: number;
  attacks?: number;
  legit?: number;
  detection_rate?: number;
  false_alarm_rate?: number;
  by_kind?: MetricsKindItem[];
  disclaimer?: string;
  disclaimer_ru?: string;
  disclaimer_kk?: string;
  disclaimer_en?: string;
}
