import type {
  Approval,
  CheckRequest,
  CheckResult,
  CreateApprovalRequest,
  DecisionRequest,
  HistoryEntry,
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

export function getErrorMessage(
  err: unknown,
  fallback = "Произошла ошибка при обращении к серверу."
): string {
  if (err instanceof ApiError) {
    return err.message;
  }
  if (err instanceof Error && err.message) {
    return err.message;
  }
  return fallback;
}

function extractValidationMessage(detail: unknown): string | null {
  if (typeof detail === "string" && detail.trim()) {
    return detail.trim();
  }
  if (Array.isArray(detail) && detail.length > 0) {
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

async function requestJson<T>(
  path: string,
  init?: RequestInit
): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  let response: Response;

  try {
    response = await fetch(url, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...init?.headers,
      },
      cache: "no-store",
    });
  } catch {
    throw new ApiError({
      status: 0,
      isNetworkError: true,
      message: `Сервер проверки платежей недоступен (${API_BASE_URL}). Убедитесь, что бэкенд запущен.`,
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
      const validationMessage = extractValidationMessage(detail);
      throw new ApiError({
        status: 422,
        detail,
        message:
          validationMessage ||
          "Проверьте корректность заполненных данных (ошибка 422).",
      });
    }

    const parsedMessage = extractValidationMessage(detail);
    throw new ApiError({
      status: response.status,
      detail,
      message:
        parsedMessage ||
        `Ошибка сервера (${response.status}). Попробуйте повторить запрос.`,
    });
  }

  return body as T;
}

export async function checkPayment(
  payload: CheckRequest
): Promise<CheckResult> {
  return requestJson<CheckResult>("/api/payments/check", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

interface RawQueueItem extends CheckRequest {
  id: string;
  check: CheckResult;
}

export async function getQueue(): Promise<QueueItem[]> {
  const raw = await requestJson<RawQueueItem[]>("/api/payments/queue", {
    method: "GET",
  });
  return raw.map((item) => ({
    id: item.id,
    request: {
      recipient_name: item.recipient_name,
      recipient_bin: item.recipient_bin,
      recipient_iik: item.recipient_iik,
      recipient_bik: item.recipient_bik,
      amount_kzt: item.amount_kzt,
      purpose: item.purpose,
    },
    result: item.check,
  }));
}

export async function getHistory(): Promise<HistoryEntry[]> {
  const raw = await requestJson<
    { payments: (HistoryEntry & { paid_at?: string })[] } | HistoryEntry[]
  >("/api/history", { method: "GET" });
  const list = Array.isArray(raw) ? raw : raw.payments;
  return list.map((p) => ({ ...p, date: p.date ?? (p as { paid_at?: string }).paid_at }));
}

export async function createApproval(
  payload: CreateApprovalRequest
): Promise<Approval> {
  return requestJson<Approval>("/api/approvals", {
    method: "POST",
    body: JSON.stringify({
      check_request: payload.request,
      accountant_note: payload.accountant_note,
    }),
  });
}

export async function getApprovals(): Promise<Approval[]> {
  return requestJson<Approval[]>("/api/approvals", {
    method: "GET",
  });
}

export async function decideApproval(
  id: string,
  payload: DecisionRequest
): Promise<Approval> {
  return requestJson<Approval>(
    `/api/approvals/${encodeURIComponent(id)}/decision`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    }
  );
}

export async function resetDemo(): Promise<void> {
  await requestJson<unknown>("/api/demo/reset", {
    method: "POST",
  });
}
