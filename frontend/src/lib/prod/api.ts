import {
  getCurrentLang,
  getDictionary,
  interpolate,
  type Lang,
} from "@/i18n";
import type {
  Approval,
  ApprovalDecision,
  ApprovalStatus,
  AuditEntry,
  AuditVerifyResult,
  Batch,
  BatchActionResult,
  CompanyDetail,
  CompanyRole,
  CompanySettings,
  CompanyUser,
  ExportFormat,
  ImportFormat,
  ImportResult,
  InviteUserResponse,
  MarkNotificationsReadResponse,
  MetricsResponse,
  NotificationList,
  NotifyOn,
  PasswordChangeResponse,
  Payment,
  PaymentInput,
  PaymentList,
  PaymentScope,
  PaymentStatus,
  ProdMeta,
  Session,
  Supplier,
  SupplierDetail,
  UserProfile,
  ValidationFieldError,
  Verdict,
} from "./types";

export const PROD_API_BASE = "/api/v1";

export class ApiError extends Error {
  status: number;
  code: string | null;
  detail: string;
  errors?: ValidationFieldError[];
  payment?: Payment;
  isNetworkError: boolean;

  constructor(options: {
    message: string;
    status: number;
    code?: string | null;
    detail?: string;
    errors?: ValidationFieldError[];
    payment?: Payment;
    isNetworkError?: boolean;
  }) {
    super(options.message);
    this.name = "ApiError";
    this.status = options.status;
    this.code = options.code ?? null;
    this.detail = options.detail ?? options.message;
    this.errors = options.errors;
    this.payment = options.payment;
    this.isNetworkError = Boolean(options.isNetworkError);
  }
}

export function isProdNetworkError(err: unknown): boolean {
  return err instanceof ApiError && err.isNetworkError;
}

export function getProdErrorMessage(err: unknown, fallback?: string): string {
  if (err instanceof ApiError) {
    return err.detail || err.message;
  }
  if (err instanceof Error && err.message) {
    return err.message;
  }
  return fallback ?? getDictionary(getCurrentLang()).errors.generic;
}

export function extractFieldErrors(err: unknown): Record<string, string> {
  if (!(err instanceof ApiError) || !Array.isArray(err.errors)) {
    return {};
  }
  const map: Record<string, string> = {};
  for (const item of err.errors) {
    if (!item || typeof item.field !== "string") continue;
    const rawField = item.field.trim();
    if (!rawField) continue;
    const normalized = rawField.includes(".")
      ? rawField.split(".").pop() || rawField
      : rawField;
    const msg = item.message?.trim() || item.message_ru?.trim();
    if (msg && !map[normalized]) {
      map[normalized] = msg;
    }
  }
  return map;
}

type UnauthorizedHandler = () => void;
let unauthorizedHandler: UnauthorizedHandler | null = null;

export function setUnauthorizedHandler(
  handler: UnauthorizedHandler | null
): void {
  unauthorizedHandler = handler;
}

function handleUnauthorized(): void {
  unauthorizedHandler?.();
}

export interface ProdRequestOptions {
  signal?: AbortSignal;
  suppressAuthRedirect?: boolean;
}

function buildUrl(
  path: string,
  lang: Lang,
  query?: Record<string, string | number | boolean | null | undefined>
): string {
  const [base, existingQuery = ""] = path.split("?");
  const params = new URLSearchParams(existingQuery);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null || value === "") continue;
      params.set(key, String(value));
    }
  }
  if (!params.has("lang")) {
    params.set("lang", lang);
  }
  return `${PROD_API_BASE}${base}?${params.toString()}`;
}

interface RawErrorPayload {
  detail?: unknown;
  code?: unknown;
  errors?: unknown;
  payment?: unknown;
}

function parseErrorPayload(
  body: unknown,
  status: number,
  lang: Lang
): {
  message: string;
  code: string | null;
  errors?: ValidationFieldError[];
  payment?: Payment;
} {
  const dict = getDictionary(lang);
  if (body && typeof body === "object") {
    const payload = body as RawErrorPayload;
    const code =
      typeof payload.code === "string" && payload.code.trim()
        ? payload.code.trim()
        : null;
    const errors = Array.isArray(payload.errors)
      ? (payload.errors.filter(
          (e): e is ValidationFieldError =>
            Boolean(e) && typeof e === "object" && "field" in e
        ) as ValidationFieldError[])
      : undefined;
    const payment =
      payload.payment && typeof payload.payment === "object"
        ? (payload.payment as Payment)
        : undefined;

    let message = "";
    if (typeof payload.detail === "string" && payload.detail.trim()) {
      message = payload.detail.trim();
    } else if (Array.isArray(payload.detail)) {
      const parts = payload.detail
        .map((item) => {
          if (typeof item === "string") return item;
          if (
            item &&
            typeof item === "object" &&
            "msg" in item &&
            typeof (item as { msg: unknown }).msg === "string"
          ) {
            return (item as { msg: string }).msg;
          }
          return null;
        })
        .filter((v): v is string => Boolean(v));
      message = parts.join("; ");
    }

    if (!message && errors && errors.length > 0) {
      message = errors
        .map((e) => e.message?.trim() || e.message_ru?.trim())
        .filter(Boolean)
        .join("; ");
    }

    if (!message) {
      message =
        status === 422
          ? dict.errors.validationDefault
          : interpolate(dict.errors.serverStatus, { status });
    }

    return { message, code, errors, payment };
  }

  if (typeof body === "string" && body.trim()) {
    return { message: body.trim(), code: null };
  }

  return {
    message: interpolate(dict.errors.serverStatus, { status }),
    code: null,
  };
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  lang: Lang = getCurrentLang(),
  query?: Record<string, string | number | boolean | null | undefined>,
  options?: ProdRequestOptions
): Promise<T> {
  const dict = getDictionary(lang);
  const method = (init.method || "GET").toUpperCase();
  const url = buildUrl(path, lang, query);

  const headers = new Headers(init.headers);
  if (method !== "GET" && method !== "HEAD" && method !== "OPTIONS") {
    headers.set("X-Shield-Request", "1");
  }
  if (
    init.body !== undefined &&
    init.body !== null &&
    !headers.has("Content-Type") &&
    typeof init.body === "string"
  ) {
    headers.set("Content-Type", "application/json");
  }

  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      method,
      headers,
      credentials: "include",
      cache: "no-store",
      signal: options?.signal ?? init.signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw err;
    }
    throw new ApiError({
      status: 0,
      code: "network_error",
      isNetworkError: true,
      message: interpolate(dict.errors.networkUnreachable, {
        url: PROD_API_BASE,
      }),
    });
  }

  if (response.status === 204) {
    return undefined as T;
  }

  let body: unknown = null;
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    try {
      body = await response.json();
    } catch {
      body = null;
    }
  } else {
    try {
      const text = await response.text();
      body = text || null;
    } catch {
      body = null;
    }
  }

  if (!response.ok) {
    const parsed = parseErrorPayload(body, response.status, lang);
    if (response.status === 401 && !options?.suppressAuthRedirect) {
      handleUnauthorized();
    }
    throw new ApiError({
      status: response.status,
      code: parsed.code,
      detail: parsed.message,
      message: parsed.message,
      errors: parsed.errors,
      payment: parsed.payment,
    });
  }

  return body as T;
}

// --- Meta & Auth ---

export async function getMeta(
  lang: Lang = getCurrentLang(),
  options?: ProdRequestOptions
): Promise<ProdMeta> {
  return request<ProdMeta>("/meta", { method: "GET" }, lang, undefined, {
    ...options,
    suppressAuthRedirect: true,
  });
}

export async function login(
  credentials: { login: string; password: string },
  lang: Lang = getCurrentLang()
): Promise<Session> {
  return request<Session>(
    "/auth/login",
    {
      method: "POST",
      body: JSON.stringify(credentials),
    },
    lang,
    undefined,
    { suppressAuthRedirect: true }
  );
}

export async function logout(lang: Lang = getCurrentLang()): Promise<void> {
  await request<void>(
    "/auth/logout",
    { method: "POST" },
    lang,
    undefined,
    { suppressAuthRedirect: true }
  );
}

export async function getMe(
  lang: Lang = getCurrentLang(),
  options?: ProdRequestOptions
): Promise<Session> {
  return request<Session>("/auth/me", { method: "GET" }, lang, undefined, {
    ...options,
    suppressAuthRedirect: options?.suppressAuthRedirect ?? true,
  });
}

// --- Payments ---

export interface GetPaymentsParams {
  scope?: PaymentScope;
  status?: PaymentStatus;
  verdict?: Verdict;
  batch_id?: string;
  supplier_id?: number;
  q?: string;
  limit?: number;
  offset?: number;
}

export async function getPayments(
  params?: GetPaymentsParams,
  lang: Lang = getCurrentLang(),
  options?: ProdRequestOptions
): Promise<PaymentList> {
  return request<PaymentList>(
    "/payments",
    { method: "GET" },
    lang,
    params
      ? {
          scope: params.scope,
          status: params.status,
          verdict: params.verdict,
          batch_id: params.batch_id,
          supplier_id: params.supplier_id,
          q: params.q,
          limit: params.limit,
          offset: params.offset,
        }
      : undefined,
    options
  );
}

export async function createPayment(
  input: PaymentInput,
  lang: Lang = getCurrentLang()
): Promise<Payment> {
  return request<Payment>(
    "/payments",
    {
      method: "POST",
      body: JSON.stringify(input),
    },
    lang
  );
}

export async function getPayment(
  id: string,
  lang: Lang = getCurrentLang(),
  options?: ProdRequestOptions
): Promise<Payment> {
  return request<Payment>(
    `/payments/${encodeURIComponent(id)}`,
    { method: "GET" },
    lang,
    undefined,
    options
  );
}

export async function updatePayment(
  id: string,
  input: PaymentInput,
  lang: Lang = getCurrentLang()
): Promise<Payment> {
  return request<Payment>(
    `/payments/${encodeURIComponent(id)}`,
    {
      method: "PUT",
      body: JSON.stringify(input),
    },
    lang
  );
}

export async function recheckPayment(
  id: string,
  lang: Lang = getCurrentLang()
): Promise<Payment> {
  return request<Payment>(
    `/payments/${encodeURIComponent(id)}/recheck`,
    { method: "POST" },
    lang
  );
}

export async function signPayment(
  id: string,
  payload?: { accountant_ack?: boolean },
  lang: Lang = getCurrentLang()
): Promise<Payment> {
  return request<Payment>(
    `/payments/${encodeURIComponent(id)}/sign`,
    {
      method: "POST",
      body: JSON.stringify(payload ?? {}),
    },
    lang
  );
}

export async function sendPaymentToDirector(
  id: string,
  accountant_note?: string,
  lang: Lang = getCurrentLang()
): Promise<Payment> {
  return request<Payment>(
    `/payments/${encodeURIComponent(id)}/send-to-director`,
    {
      method: "POST",
      body: JSON.stringify(
        accountant_note !== undefined ? { accountant_note } : {}
      ),
    },
    lang
  );
}

export async function postponePayment(
  id: string,
  note?: string,
  lang: Lang = getCurrentLang()
): Promise<Payment> {
  return request<Payment>(
    `/payments/${encodeURIComponent(id)}/postpone`,
    {
      method: "POST",
      body: JSON.stringify(note ? { note } : {}),
    },
    lang
  );
}

export async function resumePayment(
  id: string,
  lang: Lang = getCurrentLang()
): Promise<Payment> {
  return request<Payment>(
    `/payments/${encodeURIComponent(id)}/resume`,
    { method: "POST" },
    lang
  );
}

export async function cancelPayment(
  id: string,
  note?: string,
  lang: Lang = getCurrentLang()
): Promise<Payment> {
  return request<Payment>(
    `/payments/${encodeURIComponent(id)}/cancel`,
    {
      method: "POST",
      body: JSON.stringify(note ? { note } : {}),
    },
    lang
  );
}

// --- Import & Batches ---

export async function importPayments(
  file: Blob | ArrayBuffer,
  params: {
    filename: string;
    format?: ImportFormat;
    force?: boolean;
  },
  lang: Lang = getCurrentLang()
): Promise<ImportResult> {
  const body = file instanceof Blob ? await file.arrayBuffer() : file;
  return request<ImportResult>(
    "/payments/import",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/octet-stream",
      },
      body,
    },
    lang,
    {
      filename: params.filename,
      format: params.format ?? "auto",
      force: params.force ? 1 : 0,
    }
  );
}

export async function getBatches(
  limit?: number,
  lang: Lang = getCurrentLang(),
  options?: ProdRequestOptions
): Promise<Batch[]> {
  return request<Batch[]>(
    "/batches",
    { method: "GET" },
    lang,
    limit ? { limit } : undefined,
    options
  );
}

export async function batchSignGreen(
  payload?: { batch_id?: string; payment_ids?: string[] },
  lang: Lang = getCurrentLang()
): Promise<BatchActionResult> {
  return request<BatchActionResult>(
    "/payments/batch/sign-green",
    {
      method: "POST",
      body: JSON.stringify(payload ?? {}),
    },
    lang
  );
}

export async function batchSendToDirector(
  payload?: {
    batch_id?: string;
    payment_ids?: string[];
    accountant_note?: string;
  },
  lang: Lang = getCurrentLang()
): Promise<BatchActionResult> {
  return request<BatchActionResult>(
    "/payments/batch/send-to-director",
    {
      method: "POST",
      body: JSON.stringify(payload ?? {}),
    },
    lang
  );
}

// --- Approvals ---

export async function getApprovals(
  params?: { status?: ApprovalStatus },
  lang: Lang = getCurrentLang(),
  options?: ProdRequestOptions
): Promise<Approval[]> {
  return request<Approval[]>(
    "/approvals",
    { method: "GET" },
    lang,
    params?.status ? { status: params.status } : undefined,
    options
  );
}

export async function decideApproval(
  id: string,
  payload: {
    decision: ApprovalDecision;
    director_comment?: string;
    trust_account?: boolean;
  },
  lang: Lang = getCurrentLang()
): Promise<Approval> {
  return request<Approval>(
    `/approvals/${encodeURIComponent(id)}/decision`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    lang
  );
}

// --- Suppliers ---

export async function getSuppliers(
  params?: { q?: string; changed_within_days?: number },
  lang: Lang = getCurrentLang(),
  options?: ProdRequestOptions
): Promise<Supplier[]> {
  return request<Supplier[]>(
    "/suppliers",
    { method: "GET" },
    lang,
    params
      ? {
          q: params.q,
          changed_within_days: params.changed_within_days,
        }
      : undefined,
    options
  );
}

export async function getSupplier(
  id: number | string,
  lang: Lang = getCurrentLang(),
  options?: ProdRequestOptions
): Promise<SupplierDetail> {
  return request<SupplierDetail>(
    `/suppliers/${encodeURIComponent(String(id))}`,
    { method: "GET" },
    lang,
    undefined,
    options
  );
}

export async function untrustSupplierAccount(
  supplierId: number | string,
  accountId: number | string,
  comment: string,
  lang: Lang = getCurrentLang()
): Promise<SupplierDetail> {
  return request<SupplierDetail>(
    `/suppliers/${encodeURIComponent(String(supplierId))}/accounts/${encodeURIComponent(String(accountId))}/untrust`,
    {
      method: "POST",
      body: JSON.stringify({ comment }),
    },
    lang
  );
}

// --- Audit & Metrics ---

export async function getAudit(
  params?: { limit?: number; payment_id?: string; action?: string },
  lang: Lang = getCurrentLang(),
  options?: ProdRequestOptions
): Promise<AuditEntry[]> {
  return request<AuditEntry[]>(
    "/audit",
    { method: "GET" },
    lang,
    params
      ? {
          limit: params.limit,
          payment_id: params.payment_id,
          action: params.action,
        }
      : undefined,
    options
  );
}

export async function verifyAudit(
  lang: Lang = getCurrentLang(),
  options?: ProdRequestOptions
): Promise<AuditVerifyResult> {
  return request<AuditVerifyResult>(
    "/audit/verify",
    { method: "GET" },
    lang,
    undefined,
    options
  );
}

export async function getMetrics(
  lang: Lang = getCurrentLang(),
  options?: ProdRequestOptions
): Promise<MetricsResponse> {
  return request<MetricsResponse>(
    "/metrics",
    { method: "GET" },
    lang,
    undefined,
    options
  );
}

// --- Profile (/me) ---

export async function getProfile(
  lang: Lang = getCurrentLang(),
  options?: ProdRequestOptions
): Promise<UserProfile> {
  return request<UserProfile>("/me", { method: "GET" }, lang, undefined, options);
}

export async function updateProfile(
  payload: { full_name?: string; default_lang?: Lang },
  lang: Lang = getCurrentLang()
): Promise<UserProfile> {
  return request<UserProfile>(
    "/me",
    {
      method: "PUT",
      body: JSON.stringify(payload),
    },
    lang
  );
}

export async function changePassword(
  payload: { current_password: string; new_password: string },
  lang: Lang = getCurrentLang()
): Promise<PasswordChangeResponse> {
  return request<PasswordChangeResponse>(
    "/me/password",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    lang,
    undefined,
    { suppressAuthRedirect: true }
  );
}

// --- Company & Settings ---

export async function getCompany(
  lang: Lang = getCurrentLang(),
  options?: ProdRequestOptions
): Promise<CompanyDetail> {
  return request<CompanyDetail>(
    "/company",
    { method: "GET" },
    lang,
    undefined,
    options
  );
}

export async function inviteCompanyUser(
  payload: { login: string; full_name: string; role: CompanyRole },
  lang: Lang = getCurrentLang()
): Promise<InviteUserResponse> {
  return request<InviteUserResponse>(
    "/company/users",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    lang
  );
}

export async function updateCompanyUser(
  userId: number,
  payload: { role?: CompanyRole; is_active?: boolean },
  lang: Lang = getCurrentLang()
): Promise<CompanyUser> {
  return request<CompanyUser>(
    `/company/users/${encodeURIComponent(String(userId))}`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    },
    lang
  );
}

export async function getCompanySettings(
  lang: Lang = getCurrentLang(),
  options?: ProdRequestOptions
): Promise<CompanySettings> {
  return request<CompanySettings>(
    "/company/settings",
    { method: "GET" },
    lang,
    undefined,
    options
  );
}

export async function updateCompanySettings(
  payload: { notify_on?: NotifyOn; approval_threshold_kzt?: number | null },
  lang: Lang = getCurrentLang()
): Promise<CompanySettings> {
  return request<CompanySettings>(
    "/company/settings",
    {
      method: "PUT",
      body: JSON.stringify(payload),
    },
    lang
  );
}

// --- Notifications ---

export async function getNotifications(
  params?: { limit?: number },
  lang: Lang = getCurrentLang(),
  options?: ProdRequestOptions
): Promise<NotificationList> {
  return request<NotificationList>(
    "/notifications",
    { method: "GET" },
    lang,
    params?.limit ? { limit: params.limit } : undefined,
    options
  );
}

export async function markNotificationsRead(
  ids?: string[],
  lang: Lang = getCurrentLang()
): Promise<MarkNotificationsReadResponse> {
  return request<MarkNotificationsReadResponse>(
    "/notifications/read",
    {
      method: "POST",
      body: JSON.stringify(ids && ids.length > 0 ? { ids } : {}),
    },
    lang
  );
}

// --- Payments Export (CSV / PDF) ---

export interface ExportPaymentsParams {
  format: ExportFormat;
  scope?: PaymentScope;
  status?: PaymentStatus;
  verdict?: Verdict;
  batch_id?: string;
  q?: string;
  from?: string;
  to?: string;
}

export async function exportPayments(
  params: ExportPaymentsParams,
  lang: Lang = getCurrentLang()
): Promise<{ blob: Blob; filename: string }> {
  const dict = getDictionary(lang);
  const url = buildUrl("/payments/export", lang, {
    format: params.format,
    scope: params.scope,
    status: params.status,
    verdict: params.verdict,
    batch_id: params.batch_id,
    q: params.q,
    from: params.from,
    to: params.to,
  });

  let response: Response;
  try {
    response = await fetch(url, {
      method: "GET",
      credentials: "include",
      cache: "no-store",
    });
  } catch {
    throw new ApiError({
      status: 0,
      code: "network_error",
      isNetworkError: true,
      message: interpolate(dict.errors.networkUnreachable, {
        url: PROD_API_BASE,
      }),
    });
  }

  if (!response.ok) {
    let body: unknown = null;
    const ct = response.headers.get("content-type") || "";
    if (ct.includes("application/json")) {
      try {
        body = await response.json();
      } catch {
        body = null;
      }
    } else {
      try {
        body = await response.text();
      } catch {
        body = null;
      }
    }
    const parsed = parseErrorPayload(body, response.status, lang);
    if (response.status === 401) {
      handleUnauthorized();
    }
    throw new ApiError({
      status: response.status,
      code: parsed.code,
      detail: parsed.message,
      message: parsed.message,
      errors: parsed.errors,
    });
  }

  const blob = await response.blob();
  const cd = response.headers.get("content-disposition") || "";
  const match = cd.match(/filename="?([^";]+)"?/i);
  const fallbackName = `business-shield-payments.${params.format}`;
  return { blob, filename: match?.[1] || fallbackName };
}
