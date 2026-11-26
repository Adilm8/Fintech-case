import {
  getCurrentLang,
  getDictionary,
  interpolate,
  type Dictionary,
  type Lang,
} from "@/i18n";
import type {
  Approval,
  CheckRequest,
  CheckResult,
  CreateApprovalRequest,
  DecisionRequest,
  HistoryEntry,
  MetricsResponse,
  QueueItem,
} from "./types";

const RAW_API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const API_BASE_URL = RAW_API_URL.replace(/\/+$/, "");

export class ApiError extends Error {
  status: number;
  isNetworkError: boolean;
  detail?: unknown;

  constructor(options: {
    message: string;
    status: number;
    isNetworkError?: boolean;
    detail?: unknown;
  }) {
    super(options.message);
    this.name = "ApiError";
    this.status = options.status;
    this.isNetworkError = Boolean(options.isNetworkError);
    this.detail = options.detail;
  }
}

export function isNetworkUnreachableError(err: unknown): boolean {
  return err instanceof ApiError && err.isNetworkError;
}

export function getErrorMessage(err: unknown, fallback?: string): string {
  if (err instanceof ApiError) {
    return err.message;
  }
  if (err instanceof Error && err.message) {
    return err.message;
  }
  return fallback ?? getDictionary(getCurrentLang()).errors.generic;
}

function appendLangParam(path: string, lang: Lang): string {
  const [base, query = ""] = path.split("?");
  const params = new URLSearchParams(query);
  if (!params.has("lang")) {
    params.set("lang", lang);
  }
  return `${API_BASE_URL}${base}?${params.toString()}`;
}

function mapLocToMessage(loc: unknown, dict: Dictionary): string {
  if (!Array.isArray(loc)) {
    return dict.errors.validationDefault;
  }
  const joined = loc.map((part) => String(part).toLowerCase()).join(".");
  if (joined.includes("amount")) return dict.errors.validationAmount;
  if (joined.includes("iik")) return dict.errors.validationIik;
  if (joined.includes("bin")) return dict.errors.validationBin;
  if (joined.includes("bik")) return dict.errors.validationBik;
  if (joined.includes("name")) return dict.errors.validationName;
  return dict.errors.validationDefault;
}

function extractValidationMessage(
  detail: unknown,
  dict: Dictionary,
  status?: number
): string | null {
  if (typeof detail === "string" && detail.trim()) {
    return detail.trim();
  }
  if (Array.isArray(detail) && detail.length > 0) {
    if (status === 422) {
      const seen = new Set<string>();
      const mapped: string[] = [];
      for (const item of detail) {
        const msg =
          item && typeof item === "object" && "loc" in item
            ? mapLocToMessage((item as { loc: unknown }).loc, dict)
            : dict.errors.validationDefault;
        if (!seen.has(msg)) {
          seen.add(msg);
          mapped.push(msg);
        }
      }
      if (mapped.length > 0) {
        return mapped.join("; ");
      }
    }

    const messages = detail
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
      .filter((msg): msg is string => Boolean(msg));
    if (messages.length > 0) {
      return messages.join("; ");
    }
  }
  return null;
}

export interface ApiRequestOptions {
  signal?: AbortSignal;
  analyst?: boolean;
}

async function requestJson<T>(
  path: string,
  init?: RequestInit,
  lang: Lang = getCurrentLang(),
  options?: ApiRequestOptions
): Promise<T> {
  const dict = getDictionary(lang);
  const url = appendLangParam(path, lang);
  let response: Response;

  const headers = new Headers(init?.headers);
  if (
    init?.body !== undefined &&
    init?.body !== null &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }
  if (options?.analyst) {
    headers.set("X-Role", "analyst");
  }

  try {
    response = await fetch(url, {
      ...init,
      headers,
      signal: options?.signal ?? init?.signal,
      cache: "no-store",
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw err;
    }
    throw new ApiError({
      status: 0,
      isNetworkError: true,
      message: interpolate(dict.errors.networkUnreachable, {
        url: API_BASE_URL,
      }),
    });
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
    const detail =
      body && typeof body === "object" && "detail" in body
        ? (body as { detail: unknown }).detail
        : body;

    if (response.status === 422) {
      const validationMessage = extractValidationMessage(detail, dict, 422);
      throw new ApiError({
        status: 422,
        detail,
        message: validationMessage || dict.errors.validationDefault,
      });
    }

    const parsedMessage = extractValidationMessage(
      detail,
      dict,
      response.status
    );
    throw new ApiError({
      status: response.status,
      detail,
      message:
        parsedMessage ||
        interpolate(dict.errors.serverStatus, { status: response.status }),
    });
  }

  return body as T;
}

export async function checkPayment(
  payload: CheckRequest,
  lang: Lang = getCurrentLang(),
  options?: ApiRequestOptions
): Promise<CheckResult> {
  return requestJson<CheckResult>(
    "/api/payments/check",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    lang,
    options
  );
}

interface RawQueueItem extends CheckRequest {
  id: string;
  check: CheckResult;
}

export async function getQueue(
  lang: Lang = getCurrentLang(),
  options?: ApiRequestOptions
): Promise<QueueItem[]> {
  const raw = await requestJson<RawQueueItem[]>(
    "/api/payments/queue",
    {
      method: "GET",
    },
    lang,
    options
  );
  return raw.map((item) => ({
    id: item.id,
    request: {
      ...(item.payer_id !== undefined ? { payer_id: item.payer_id } : {}),
      recipient_name: item.recipient_name,
      recipient_bin: item.recipient_bin,
      recipient_iik: item.recipient_iik,
      recipient_bik: item.recipient_bik,
      amount_kzt: item.amount_kzt,
      purpose: item.purpose,
      ...(item.kbe ? { kbe: item.kbe } : {}),
      ...(item.knp ? { knp: item.knp } : {}),
    },
    result: item.check,
  }));
}

export async function getHistory(
  lang: Lang = getCurrentLang()
): Promise<HistoryEntry[]> {
  const raw = await requestJson<
    { payments: (HistoryEntry & { paid_at?: string })[] } | HistoryEntry[]
  >("/api/history", { method: "GET" }, lang);
  const list = Array.isArray(raw) ? raw : raw.payments;
  return list.map((p) => ({
    ...p,
    date: p.date ?? (p as { paid_at?: string }).paid_at,
  }));
}

interface RawApproval extends Omit<Approval, "request"> {
  request?: CheckRequest;
  check_request?: CheckRequest;
}

function adaptApproval(raw: RawApproval): Approval {
  const request = raw.request ?? raw.check_request;
  return {
    id: raw.id,
    ...(request ? { request } : {}),
    check: raw.check,
    status: raw.status,
    accountant_note: raw.accountant_note,
    director_comment: raw.director_comment,
    trust_account: raw.trust_account,
    decided_at: raw.decided_at,
    ...(raw.created_at !== undefined ? { created_at: raw.created_at } : {}),
  };
}

export async function createApproval(
  payload: CreateApprovalRequest,
  lang: Lang = getCurrentLang(),
  options?: ApiRequestOptions
): Promise<Approval> {
  const raw = await requestJson<RawApproval>(
    "/api/approvals",
    {
      method: "POST",
      body: JSON.stringify({
        check_request: payload.request,
        accountant_note: payload.accountant_note,
      }),
    },
    lang,
    options
  );
  return adaptApproval(raw);
}

export async function getApprovals(
  lang: Lang = getCurrentLang(),
  options?: ApiRequestOptions
): Promise<Approval[]> {
  const raw = await requestJson<RawApproval[]>(
    "/api/approvals",
    {
      method: "GET",
    },
    lang,
    options
  );
  return raw.map(adaptApproval);
}

export async function decideApproval(
  id: string,
  payload: DecisionRequest,
  lang: Lang = getCurrentLang(),
  options?: ApiRequestOptions
): Promise<Approval> {
  const dict = getDictionary(lang);
  try {
    const raw = await requestJson<RawApproval>(
      `/api/approvals/${encodeURIComponent(id)}/decision`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
      lang,
      options
    );
    return adaptApproval(raw);
  } catch (err) {
    if (err instanceof ApiError) {
      if (err.status === 409) {
        throw new ApiError({
          status: 409,
          detail: err.detail,
          message: dict.errors.approvalAlreadyProcessed,
        });
      }
      if (err.status === 422) {
        const detailText =
          typeof err.detail === "string" && err.detail.trim()
            ? err.detail.trim()
            : dict.errors.approvalActionUnavailable;
        throw new ApiError({
          status: 422,
          detail: err.detail,
          message: detailText,
        });
      }
    }
    throw err;
  }
}

export async function getMetrics(
  lang: Lang = getCurrentLang(),
  options?: { signal?: AbortSignal }
): Promise<MetricsResponse> {
  return requestJson<MetricsResponse>(
    "/api/metrics",
    {
      method: "GET",
      signal: options?.signal,
    },
    lang
  );
}

export async function resetDemo(lang: Lang = getCurrentLang()): Promise<void> {
  await requestJson<unknown>(
    "/api/demo/reset",
    {
      method: "POST",
    },
    lang
  );
}
