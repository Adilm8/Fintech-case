/**
 * Клиент локального подписания через NCALayer (НУЦ РК) с автоматическим fallback
 * на демонстрационную серверную имитацию подписи.
 *
 * БЕЗОПАСНОСТЬ:
 * - Код НИКОГДА не запрашивает, не хранит, не передаёт и не логирует PIN-коды,
 *   пароли и закрытые ключи ЭЦП.
 * - Выбор ключевого хранилища (PKCS12 / токен) и ввод пароля выполняются
 *   исключительно в собственном локальном окне приложения NCALayer.
 */

import {
  getCurrentLang,
  getDictionary,
  interpolate,
  type Lang,
} from "@/i18n";
import { ApiError, PROD_API_BASE } from "./api";
import type {
  Payment,
  SignerKind,
  SignRequestBody,
  ValidationFieldError,
} from "./types";

export const NCALAYER_URL = "wss://127.0.0.1:13579";
export const NCALAYER_COMMON_UTILS_MODULE = "kz.gov.pki.knca.commonUtils";
export const DEFAULT_NCALAYER_CONNECT_TIMEOUT_MS = 1500;
export const DEFAULT_NCALAYER_SIGN_TIMEOUT_MS = 60_000;

export type { SignerKind, SignRequestBody };

export interface SignDocumentOutcome {
  signer: SignerKind;
  signature: string;
  simulated: boolean;
}

export interface SignPaymentDocumentResult<TResponse = Payment>
  extends SignDocumentOutcome {
  payment: TResponse;
}

export interface NcaLayerSignOptions {
  /** Таймаут установления WebSocket-соединения с NCALayer (по умолчанию 1500 мс). */
  timeoutMs?: number;
  /** Таймаут ожидания подтверждения подписи в окне NCALayer (по умолчанию 60000 мс). */
  signTimeoutMs?: number;
  /** Тип хранилища ключей NCALayer (по умолчанию PKCS12). */
  storageName?: string;
  /** Включать ли подписанный digest в CMS-контейнер (по умолчанию true). */
  attachData?: boolean;
}

export type SignPaymentPoster<TResponse = Payment> = (
  paymentId: string,
  body: SignRequestBody
) => Promise<TResponse>;

export interface SignPaymentDocumentOptions<TResponse = Payment>
  extends NcaLayerSignOptions {
  /** Явное подтверждение бухгалтера для yellow/grey вердиктов. */
  accountantAck?: boolean;
  /** Язык локализованного ответа API. */
  lang?: Lang;
  /** AbortSignal для HTTP-запроса подписания (если используется встроенный клиент). */
  signal?: AbortSignal;
  /** Принудительно пропустить попытку подключения к NCALayer и использовать имитацию. */
  preferSimulated?: boolean;
  /**
   * Инъектируемый колбэк отправки POST /api/v1/payments/{id}/sign.
   * Позволяет использовать обновлённую функцию signPayment из api.ts без дублирования fetch.
   */
  post?: SignPaymentPoster<TResponse>;
}

interface NcaLayerVersionMessage {
  result?: {
    version?: string;
  };
}

interface NcaLayerResponseMessage {
  code?: string;
  message?: string;
  responseObject?: unknown;
}

interface RawApiErrorBody {
  detail?: unknown;
  code?: unknown;
  errors?: unknown;
  payment?: unknown;
}

function safeCloseSocket(ws: WebSocket | null): void {
  if (!ws) return;
  try {
    if (
      ws.readyState === WebSocket.CONNECTING ||
      ws.readyState === WebSocket.OPEN
    ) {
      ws.close();
    }
  } catch {
    // Игнорируем ошибки закрытия сокета.
  }
}

function encodeUtf8ToBase64(text: string): string {
  const bytes = new TextEncoder().encode(text);
  let binary = "";
  for (let i = 0; i < bytes.length; i += 1) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

/**
 * Попытаться открыть локальное WebSocket-соединение с NCALayer с таймаутом.
 * При таймауте, ошибке или отсутствии WebSocket аккуратно закрывает сокет
 * и возвращает null (исключения наружу не пробрасываются).
 */
export function connectNcaLayer(
  timeoutMs: number = DEFAULT_NCALAYER_CONNECT_TIMEOUT_MS
): Promise<WebSocket | null> {
  if (typeof window === "undefined" || typeof WebSocket === "undefined") {
    return Promise.resolve(null);
  }

  return new Promise<WebSocket | null>((resolve) => {
    let settled = false;
    let ws: WebSocket | null = null;

    const finish = (socket: WebSocket | null) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timerId);
      if (ws && socket === null) {
        ws.onopen = null;
        ws.onerror = null;
        ws.onclose = null;
        safeCloseSocket(ws);
      }
      resolve(socket);
    };

    const timerId = window.setTimeout(() => {
      finish(null);
    }, Math.max(100, timeoutMs));

    try {
      ws = new WebSocket(NCALAYER_URL);
    } catch {
      finish(null);
      return;
    }

    ws.onopen = () => {
      if (!ws) {
        finish(null);
        return;
      }
      ws.onopen = null;
      ws.onerror = null;
      ws.onclose = null;
      finish(ws);
    };

    ws.onerror = () => {
      finish(null);
    };

    ws.onclose = () => {
      finish(null);
    };
  });
}

/**
 * Запросить CMS/PKCS#7 подпись дайджеста документа через локальный NCALayer.
 * Выбор сертификата и ввод пароля происходят ТОЛЬКО в окне NCALayer.
 * Если NCALayer недоступен, пользователь отменил подписание или произошла ошибка —
 * возвращает null (без выброса исключения).
 */
export async function signDigestWithNcaLayer(
  documentDigest: string,
  opts?: NcaLayerSignOptions
): Promise<string | null> {
  if (!documentDigest.trim()) {
    return null;
  }

  const ws = await connectNcaLayer(
    opts?.timeoutMs ?? DEFAULT_NCALAYER_CONNECT_TIMEOUT_MS
  );
  if (!ws) {
    return null;
  }

  const storageName = opts?.storageName ?? "PKCS12";
  const attachData = opts?.attachData ?? true;
  const signTimeoutMs = opts?.signTimeoutMs ?? DEFAULT_NCALAYER_SIGN_TIMEOUT_MS;
  const base64Data = encodeUtf8ToBase64(documentDigest);

  return new Promise<string | null>((resolve) => {
    let settled = false;

    const finish = (cmsBase64: string | null) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timerId);
      ws.onmessage = null;
      ws.onerror = null;
      ws.onclose = null;
      safeCloseSocket(ws);
      resolve(cmsBase64);
    };

    const timerId = window.setTimeout(() => {
      finish(null);
    }, Math.max(1000, signTimeoutMs));

    ws.onmessage = (event: MessageEvent<unknown>) => {
      if (typeof event.data !== "string") {
        return;
      }
      let parsed: NcaLayerVersionMessage & NcaLayerResponseMessage;
      try {
        parsed = JSON.parse(event.data) as NcaLayerVersionMessage &
          NcaLayerResponseMessage;
      } catch {
        finish(null);
        return;
      }

      // Первым пакетом после подключения NCALayer присылает свою версию (без поля code).
      if (parsed.code === undefined && parsed.result?.version !== undefined) {
        return;
      }

      if (
        parsed.code === "200" &&
        typeof parsed.responseObject === "string" &&
        parsed.responseObject.trim().length > 0
      ) {
        finish(parsed.responseObject.trim());
        return;
      }

      finish(null);
    };

    ws.onerror = () => {
      finish(null);
    };

    ws.onclose = () => {
      finish(null);
    };

    try {
      const command = {
        module: NCALAYER_COMMON_UTILS_MODULE,
        method: "createCMSSignatureFromBase64",
        args: [storageName, "SIGNATURE", base64Data, attachData],
      };
      ws.send(JSON.stringify(command));
    } catch {
      finish(null);
    }
  });
}

function parseSignError(
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
    const payload = body as RawApiErrorBody;
    const code =
      typeof payload.code === "string" && payload.code.trim()
        ? payload.code.trim()
        : null;
    const errors = Array.isArray(payload.errors)
      ? (payload.errors.filter(
          (item): item is ValidationFieldError =>
            Boolean(item) && typeof item === "object" && "field" in item
        ) as ValidationFieldError[])
      : undefined;
    const payment =
      payload.payment && typeof payload.payment === "object"
        ? (payload.payment as Payment)
        : undefined;

    let message = "";
    if (typeof payload.detail === "string" && payload.detail.trim()) {
      message = payload.detail.trim();
    }
    if (!message) {
      message =
        status === 422
          ? dict.errors.validationDefault
          : interpolate(dict.errors.serverStatus, { status });
    }
    return { message, code, errors, payment };
  }

  return {
    message: interpolate(dict.errors.serverStatus, { status }),
    code: null,
  };
}

/**
 * Fallback-отправка POST /api/v1/payments/{id}/sign в точном стиле api.ts
 * (заголовок X-Shield-Request, credentials: include, ApiError с code/payment).
 * Используется, если вызывающий код не передал собственный колбэк opts.post.
 */
async function defaultPostSignPayment<TResponse>(
  paymentId: string,
  body: SignRequestBody,
  lang: Lang,
  signal?: AbortSignal
): Promise<TResponse> {
  const dict = getDictionary(lang);
  const params = new URLSearchParams({ lang });
  const url = `${PROD_API_BASE}/payments/${encodeURIComponent(paymentId)}/sign?${params.toString()}`;

  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Shield-Request": "1",
      },
      credentials: "include",
      cache: "no-store",
      body: JSON.stringify(body),
      signal,
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

  let parsedBody: unknown = null;
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    try {
      parsedBody = await response.json();
    } catch {
      parsedBody = null;
    }
  } else {
    try {
      const text = await response.text();
      parsedBody = text || null;
    } catch {
      parsedBody = null;
    }
  }

  if (!response.ok) {
    const parsedErr = parseSignError(parsedBody, response.status, lang);
    throw new ApiError({
      status: response.status,
      code: parsedErr.code,
      detail: parsedErr.message,
      message: parsedErr.message,
      errors: parsedErr.errors,
      payment: parsedErr.payment,
    });
  }

  return parsedBody as TResponse;
}

/**
 * Подписать платёжный документ с привязкой к documentDigest:
 * 1. Пытается получить CMS-подпись через локальный NCALayer.
 * 2. Если NCALayer недоступен или вернул ошибку — переключается на демонстрационную
 *    имитацию (signer: "simulated"). Клиент не владеет локальным секретом компании,
 *    поэтому в режиме simulated поле signature отправляется пустой строкой, а сервер
 *    на POST /api/v1/payments/{id}/sign проверяет document_digest, вычисляет
 *    имитированную HMAC-подпись и фиксирует её в журнале аудита.
 */
export async function signPaymentDocument<TResponse = Payment>(
  paymentId: string,
  documentDigest: string,
  opts?: SignPaymentDocumentOptions<TResponse>
): Promise<SignPaymentDocumentResult<TResponse>> {
  const cmsSignature = opts?.preferSimulated
    ? null
    : await signDigestWithNcaLayer(documentDigest, {
        timeoutMs: opts?.timeoutMs,
        signTimeoutMs: opts?.signTimeoutMs,
        storageName: opts?.storageName,
        attachData: opts?.attachData,
      });

  const simulated = cmsSignature === null;
  const signer: SignerKind = simulated ? "simulated" : "ncalayer";
  // В режиме simulated секрет хранится только на сервере, поэтому клиент отправляет "".
  const signature = cmsSignature ?? "";

  const requestBody: SignRequestBody = {
    document_digest: documentDigest,
    signature,
    signer,
    ...(opts?.accountantAck !== undefined
      ? { accountant_ack: opts.accountantAck }
      : {}),
  };

  const lang = opts?.lang ?? getCurrentLang();
  const payment = opts?.post
    ? await opts.post(paymentId, requestBody)
    : await defaultPostSignPayment<TResponse>(
        paymentId,
        requestBody,
        lang,
        opts?.signal
      );

  return {
    signer,
    signature,
    simulated,
    payment,
  };
}
