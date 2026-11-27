import type { Lang } from "@/i18n";
import type {
  CheckRequest,
  CheckResult,
  MetricsResponse,
  Verdict,
} from "@/lib/types";

export type { CheckRequest, CheckResult, MetricsResponse, Verdict };

export type Role = "accountant" | "director" | "analyst";

export type PaymentStatus =
  | "checked"
  | "pending_approval"
  | "approved"
  | "rejected"
  | "postponed"
  | "signed"
  | "cancelled";

export type PaymentSource = "manual" | "1c" | "csv" | "seed";

export type ApprovalStatus = "pending" | "approved" | "rejected" | "superseded";

export type ApprovalDecision = "approved" | "rejected";

export type PaymentScope = "queue" | "signed" | "all";

export type ImportFormat = "auto" | "1c" | "csv";

export type SignerKind = "simulated" | "ncalayer";

export interface SignRequestBody {
  document_digest: string;
  signature: string;
  signer: SignerKind;
  accountant_ack?: boolean;
}

export const REQUISITES_CHANGED_BADGE_DAYS = 90;
export const MIN_DIRECTOR_COMMENT_LENGTH = 10;
export const MAX_IMPORT_FILE_BYTES = 2 * 1024 * 1024;

export interface ProdMeta {
  mode: "prod";
  ruleset_version: string;
}

export interface User {
  id: number;
  login: string;
  full_name: string;
  role: Role;
  company_id: string | null;
}

export interface UserBrief {
  id: number;
  login: string;
  full_name: string;
  role: Role;
}

export interface Company {
  id: string;
  name: string;
  bin: string;
  iik: string;
  bik: string;
}

export interface Session {
  user: User;
  company: Company | null;
  must_change_password?: boolean;
}

export interface PaymentInput {
  recipient_name: string;
  recipient_bin: string;
  recipient_iik: string;
  recipient_bik: string;
  amount_kzt: number;
  purpose: string;
  kbe?: string;
  knp?: string;
  doc_number?: string;
  doc_date?: string | null;
}

export interface PaymentPermissions {
  can_edit: boolean;
  can_sign: boolean;
  sign_requires_ack: boolean;
  sign_block_code: string | null;
  can_send_to_director: boolean;
  can_postpone: boolean;
  can_resume: boolean;
  can_cancel: boolean;
  can_decide: boolean;
}

export interface ApprovalBrief {
  id: string;
  status: ApprovalStatus;
  accountant_note: string;
  director_comment: string | null;
  trust_account: boolean;
  created_by: UserBrief;
  created_at: string;
  decided_by: UserBrief | null;
  decided_at: string | null;
}

export interface SupplierRef {
  id: number | null;
  known: boolean;
  account_known: boolean;
  requisites_changed_days_ago: number | null;
}

export interface Payment {
  id: string;
  company_id: string;
  status: PaymentStatus;
  source: PaymentSource;
  batch_id: string | null;
  line_no: number | null;
  doc_number: string;
  doc_date: string | null;
  request: CheckRequest;
  check: CheckResult;
  document_digest?: string | null;
  approval: ApprovalBrief | null;
  accountant_ack: boolean;
  supplier: SupplierRef;
  duplicate_of: string | null;
  permissions: PaymentPermissions;
  created_by: UserBrief;
  created_at: string;
  updated_at: string;
  signed_by: UserBrief | null;
  signed_at: string | null;
}

export interface VerdictCounts {
  green: number;
  yellow: number;
  red: number;
  grey: number;
  invalid: number;
}

export interface PaymentList {
  items: Payment[];
  total: number;
  counts: {
    by_status: Record<PaymentStatus, number>;
    by_verdict: VerdictCounts;
  };
}

export interface Batch {
  id: string;
  source: "1c" | "csv";
  filename: string;
  total: number;
  created_count: number;
  failed_count: number;
  created_by: UserBrief;
  created_at: string;
}

export interface ImportLineError {
  line_no: number | null;
  doc_number: string | null;
  code: string;
  message: string;
}

export interface ImportResult {
  batch: Batch;
  items: Payment[];
  errors: ImportLineError[];
  summary: {
    total: number;
    created: number;
    failed: number;
    duplicates: number;
    by_verdict: VerdictCounts;
  };
}

export interface BatchSkippedItem {
  id: string;
  code: string;
  detail: string;
}

export interface BatchActionResult {
  done: Payment[];
  skipped: BatchSkippedItem[];
}

export interface Approval {
  id: string;
  payment_id: string;
  request: CheckRequest;
  check: CheckResult;
  status: ApprovalStatus;
  accountant_note: string;
  director_comment: string | null;
  trust_account: boolean;
  can_trust: boolean;
  created_by: UserBrief;
  created_at: string;
  decided_by: UserBrief | null;
  decided_at: string | null;
}

export interface Supplier {
  id: number;
  bin: string;
  name: string;
  first_seen_at: string;
  last_payment_at: string | null;
  payments_count: number;
  total_paid_kzt: number;
  accounts_count: number;
  requisites_changed_at: string | null;
  requisites_changed_days_ago: number | null;
  has_pending_change: boolean;
  trusted_accounts_count: number;
}

export interface SupplierAccount {
  id: number;
  iik: string;
  bik: string;
  bank_name: string | null;
  first_seen_at: string;
  last_used_at: string;
  payments_count: number;
  trusted: boolean;
  trusted_at: string | null;
  trusted_comment: string | null;
}

export interface SupplierChange {
  id: number;
  kind: "account_added" | "bank_changed" | "name_changed";
  old_value: string | null;
  new_value: string;
  occurred_at: string;
  payment_id: string | null;
}

export interface SupplierDetail extends Supplier {
  accounts: SupplierAccount[];
  changes: SupplierChange[];
  payments: Payment[];
}

export interface AuditEntry {
  id: number;
  timestamp: string;
  user: { id: number; login: string; role: Role } | null;
  action: string;
  payment_id: string | null;
  approval_id: string | null;
  check_id: string | null;
  batch_id: string | null;
  request_sha256: string | null;
  ruleset_version: string | null;
  verdict: Verdict | null;
  signal_ids: string[];
  details: Record<string, unknown>;
  entry_hash: string;
}

export interface AuditVerifyResult {
  ok: boolean;
  checked: number;
  broken_at: number | null;
}

export interface ValidationFieldError {
  field: string;
  message: string;
  message_ru?: string;
}

export type CompanyRole = "accountant" | "director";
export type NotifyOn = "red" | "red_yellow";
export type ExportFormat = "csv" | "pdf";
export type NotificationKind =
  | "approval_pending"
  | "approval_approved"
  | "approval_rejected"
  | "sign_denied";

export interface UserProfile {
  id: number;
  login: string;
  full_name: string;
  role: Role;
  company_id: string | null;
  default_lang: Lang;
  company: Company | null;
}

export interface PasswordChangeResponse {
  ok: boolean;
  revoked_sessions: number;
}

export interface CompanyUser {
  id: number;
  login: string;
  full_name: string;
  role: CompanyRole;
  is_active: boolean;
  default_lang: Lang;
  created_at: string;
}

export interface CompanyDetail {
  id: string;
  name: string;
  bin: string;
  iik: string;
  bik: string;
  created_at: string;
  users: CompanyUser[];
}

export interface InviteUserResponse {
  user: CompanyUser;
  temporary_password: string;
}

export interface CompanySettings {
  notify_on: NotifyOn;
  approval_threshold_kzt: number | null;
  updated_at: string | null;
}

export interface NotificationItem {
  id: string;
  kind: NotificationKind;
  title: string;
  message: string;
  created_at: string;
  read: boolean;
  payment_id: string | null;
  approval_id: string | null;
  verdict: Verdict | null;
  recipient_name: string | null;
  amount_kzt: number | null;
  link: string | null;
}

export interface NotificationList {
  unread_count: number;
  items: NotificationItem[];
}

export interface MarkNotificationsReadResponse {
  marked: number;
  unread_count: number;
}
