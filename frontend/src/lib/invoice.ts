import {
  getCurrentLang,
  getDictionary,
  interpolate,
  type Dictionary,
  type Lang,
} from "@/i18n";
import { API_BASE_URL } from "@/lib/api";
import { parseKztString } from "@/lib/format";
import { IS_PROD } from "@/lib/mode";

export const ALLOWED_INVOICE_MIME_TYPES = [
  "application/pdf",
  "image/png",
  "image/jpeg",
  "image/webp",
] as const;

export type InvoiceMimeType = (typeof ALLOWED_INVOICE_MIME_TYPES)[number];

export const MAX_INVOICE_FILE_BYTES = 10 * 1024 * 1024;
export const INVOICE_LOW_CONFIDENCE_THRESHOLD = 0.5;
export const INVOICE_EXTRACT_TIMEOUT_MS = 60_000;

export const INVOICE_ACCEPT_ATTRIBUTE =
  "application/pdf,image/png,image/jpeg,image/webp,.pdf,.png,.jpg,.jpeg,.webp";

const ALLOWED_MIME_SET = new Set<string>(ALLOWED_INVOICE_MIME_TYPES);

const EXTENSION_TO_MIME: Record<string, InvoiceMimeType> = {
  ".pdf": "application/pdf",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
};

/**
 * Source values returned by the invoice extraction API.
 * UI layers must map these to neutral localized labels (never model/vendor names).
 */
export type InvoiceExtractionSource = "claude" | "text_rules" | "none";

export interface InvoiceExtraction {
  recipient_name: string | null;
  recipient_bin: string | null;
  recipient_iik: string | null;
  recipient_bik: string | null;
  amount_kzt: number | null;
  purpose: string | null;
  invoice_number: string | null;
  invoice_date: string | null;
  kbe: string | null;
  knp: string | null;
  currency: string | null;
  confidence: number;
  warnings: string[];
  source: InvoiceExtractionSource;
}

export interface InvoiceMappedFormValues {
  recipient_name?: string;
  recipient_bin?: string;
  recipient_iik?: string;
  recipient_bik?: string;
  amount_kzt?: string;
  purpose?: string;
  kbe?: string;
  knp?: string;
  doc_number?: string;
  doc_date?: string;
}

export type InvoiceValidationErrorCode =
  | "empty_file"
  | "too_large"
  | "unsupported_type";

export type InvoiceValidationResult =
  | { ok: true; mimeType: InvoiceMimeType }
  | { ok: false; code: InvoiceValidationErrorCode; message: string };

export type InvoiceExtractErrorCode =
  | InvoiceValidationErrorCode
  | "missing_api_base"
  | "network"
  | "timeout"
  | "http_400"
  | "http_413"
  | "http_415"
  | "http_other"
  | "invalid_response";

export class InvoiceExtractError extends Error {
  code: InvoiceExtractErrorCode;
  status: number;
  detail?: unknown;

  constructor(options: {
    code: InvoiceExtractErrorCode;
    message: string;
    status?: number;
    detail?: unknown;
  }) {
    super(options.message);
    this.name = "InvoiceExtractError";
    this.code = options.code;
    this.status = options.status ?? 0;
    this.detail = options.detail;
  }
}

export function isInvoiceExtractAbortError(err: unknown): boolean {
  return (
    (err instanceof DOMException && err.name === "AbortError") ||
    (err instanceof Error && err.name === "AbortError")
  );
}

export function getInvoiceErrorMessage(
  err: unknown,
  lang: Lang = getCurrentLang()
): string {
  if (err instanceof InvoiceExtractError) {
    return err.message;
  }
  if (err instanceof Error && err.message) {
    return err.message;
  }
  return getDictionary(lang).invoice.errors.generic;
}

function resolveMimeTypeFromExtension(filename: string): InvoiceMimeType | null {
  const lower = filename.trim().toLowerCase();
  const dotIdx = lower.lastIndexOf(".");
  if (dotIdx === -1) return null;
  const ext = lower.slice(dotIdx);
  return EXTENSION_TO_MIME[ext] ?? null;
}

export function resolveInvoiceMimeType(file: File): InvoiceMimeType | null {
  const rawType = (file.type || "").trim().toLowerCase();
  if (rawType === "image/jpg") {
    return "image/jpeg";
  }
  if (rawType && ALLOWED_MIME_SET.has(rawType)) {
    return rawType as InvoiceMimeType;
  }
  // Only fall back to filename extension when browser omitted file.type.
  if (!rawType) {
    return resolveMimeTypeFromExtension(file.name || "");
  }
  return null;
}

export function validateInvoiceFile(
  file: File,
  lang: Lang = getCurrentLang()
): InvoiceValidationResult {
  const dict = getDictionary(lang);

  if (file.size <= 0) {
    return {
      ok: false,
      code: "empty_file",
      message: dict.invoice.errors.emptyFile,
    };
  }

  if (file.size > MAX_INVOICE_FILE_BYTES) {
    return {
      ok: false,
      code: "too_large",
      message: dict.invoice.errors.tooLarge,
    };
  }

  const mimeType = resolveInvoiceMimeType(file);
  if (!mimeType) {
    return {
      ok: false,
      code: "unsupported_type",
      message: dict.invoice.errors.unsupportedType,
    };
  }

  return { ok: true, mimeType };
}

function normalizeApiBase(raw: string | null | undefined): string {
  if (typeof raw !== "string") return "";
  const trimmed = raw.trim().replace(/\/+$/, "");
  if (!trimmed) return "";
  if (
    trimmed.startsWith("http://") ||
    trimmed.startsWith("https://") ||
    trimmed.startsWith("/")
  ) {
    return trimmed;
  }
  return "";
}

/**
 * Resolves the API base URL for `/api/invoice/extract`.
 * `next.config.ts` only rewrites `/api/v1/*`, so both demo and prod call `NEXT_PUBLIC_API_URL`
 * directly with `credentials: "omit"`. If unset in prod on a non-localhost host, returns ""
 * so callers surface a clear localized error instead of crashing.
 */
export function getInvoiceApiBase(): string {
  const configured = normalizeApiBase(process.env.NEXT_PUBLIC_API_URL);
  if (configured) {
    return configured;
  }
  if (!IS_PROD) {
    return normalizeApiBase(API_BASE_URL);
  }
  if (
    typeof window !== "undefined" &&
    (window.location.hostname === "localhost" ||
      window.location.hostname === "127.0.0.1")
  ) {
    return normalizeApiBase(API_BASE_URL);
  }
  return "";
}

const VENDOR_TERMS_RE =
  /\b(claude|anthropic|openai|gemini|chatgpt|gpt-?\d*|llm|artificial intelligence)\b/i;

function extractDetailText(detail: unknown): string | null {
  if (typeof detail === "string") {
    const trimmed = detail.trim();
    return trimmed || null;
  }
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (typeof item === "string") return item.trim();
        if (
          item &&
          typeof item === "object" &&
          "msg" in item &&
          typeof (item as { msg: unknown }).msg === "string"
        ) {
          return (item as { msg: string }).msg.trim();
        }
        return "";
      })
      .filter(Boolean);
    return parts.length > 0 ? parts.join("; ") : null;
  }
  if (
    detail &&
    typeof detail === "object" &&
    "message" in detail &&
    typeof (detail as { message: unknown }).message === "string"
  ) {
    const trimmed = (detail as { message: string }).message.trim();
    return trimmed || null;
  }
  return null;
}

function buildHttpError(
  status: number,
  detail: unknown,
  dict: Dictionary
): InvoiceExtractError {
  const rawDetailText = extractDetailText(detail);
  const safeDetailText =
    rawDetailText && !VENDOR_TERMS_RE.test(rawDetailText)
      ? rawDetailText
      : null;

  if (status === 400) {
    return new InvoiceExtractError({
      code: "http_400",
      status,
      detail,
      message: safeDetailText || dict.invoice.errors.http400,
    });
  }
  if (status === 413) {
    return new InvoiceExtractError({
      code: "http_413",
      status,
      detail,
      message: safeDetailText || dict.invoice.errors.http413,
    });
  }
  if (status === 415) {
    return new InvoiceExtractError({
      code: "http_415",
      status,
      detail,
      message: safeDetailText || dict.invoice.errors.http415,
    });
  }

  return new InvoiceExtractError({
    code: "http_other",
    status,
    detail,
    message:
      safeDetailText ||
      interpolate(dict.invoice.errors.httpOther, { status }),
  });
}

function parseNullableString(value: unknown): string | null {
  if (typeof value === "string") {
    const trimmed = value.trim();
    return trimmed.length > 0 ? trimmed : null;
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    return String(value);
  }
  return null;
}

function parseNullableAmount(value: unknown): number | null {
  if (typeof value === "number") {
    return Number.isFinite(value) && value > 0 ? value : null;
  }
  if (typeof value === "string") {
    const parsed = parseKztString(value);
    return parsed !== null && Number.isFinite(parsed) && parsed > 0
      ? parsed
      : null;
  }
  return null;
}

function parseConfidence(value: unknown): number {
  let num = Number.NaN;
  if (typeof value === "number") {
    num = value;
  } else if (typeof value === "string" && value.trim()) {
    num = Number(value.trim().replace(",", "."));
  }
  if (!Number.isFinite(num)) {
    return 0;
  }
  return Math.min(1, Math.max(0, num));
}

function parseWarnings(value: unknown): string[] {
  if (Array.isArray(value)) {
    const out: string[] = [];
    for (const item of value) {
      if (typeof item === "string") {
        const trimmed = item.trim();
        if (trimmed) out.push(trimmed);
      } else if (
        item &&
        typeof item === "object" &&
        "message" in item &&
        typeof (item as { message: unknown }).message === "string"
      ) {
        const trimmed = (item as { message: string }).message.trim();
        if (trimmed) out.push(trimmed);
      } else if (typeof item === "number" || typeof item === "boolean") {
        out.push(String(item));
      }
    }
    return out;
  }
  if (typeof value === "string" && value.trim()) {
    return [value.trim()];
  }
  return [];
}

function parseSource(value: unknown): InvoiceExtractionSource {
  if (value === "claude" || value === "text_rules" || value === "none") {
    return value;
  }
  return "none";
}

export function parseInvoiceExtraction(
  raw: unknown,
  lang: Lang = getCurrentLang()
): InvoiceExtraction {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    throw new InvoiceExtractError({
      code: "invalid_response",
      status: 200,
      message: getDictionary(lang).invoice.errors.invalidResponse,
    });
  }

  const record = raw as Record<string, unknown>;

  return {
    recipient_name: parseNullableString(record.recipient_name),
    recipient_bin: parseNullableString(record.recipient_bin),
    recipient_iik: parseNullableString(record.recipient_iik),
    recipient_bik: parseNullableString(record.recipient_bik),
    amount_kzt: parseNullableAmount(record.amount_kzt),
    purpose: parseNullableString(record.purpose),
    invoice_number: parseNullableString(record.invoice_number),
    invoice_date: parseNullableString(record.invoice_date),
    kbe: parseNullableString(record.kbe),
    knp: parseNullableString(record.knp),
    currency: parseNullableString(record.currency),
    confidence: parseConfidence(record.confidence),
    warnings: parseWarnings(record.warnings),
    source: parseSource(record.source),
  };
}

export function needsManualConfirmation(result: InvoiceExtraction): boolean {
  return (
    result.confidence < INVOICE_LOW_CONFIDENCE_THRESHOLD ||
    result.warnings.length > 0 ||
    result.source === "none"
  );
}

function sanitizeDigits(value: string): string {
  return value.replace(/\s+/g, "").replace(/\D+/g, "");
}

function sanitizeCode(value: string): string {
  return value.replace(/\s+/g, "").toUpperCase();
}

function normalizeIsoDateForInput(raw: string): string | null {
  const trimmed = raw.trim();

  const isoMatch = /^(\d{4})-(\d{2})-(\d{2})(?:$|T|\s)/.exec(trimmed);
  if (isoMatch) {
    const year = Number(isoMatch[1]);
    const month = Number(isoMatch[2]);
    const day = Number(isoMatch[3]);
    if (month >= 1 && month <= 12 && day >= 1 && day <= 31 && year >= 1900) {
      return `${isoMatch[1]}-${isoMatch[2]}-${isoMatch[3]}`;
    }
    return null;
  }

  const dmyMatch = /^(\d{2})[./](\d{2})[./](\d{4})$/.exec(trimmed);
  if (dmyMatch) {
    const day = Number(dmyMatch[1]);
    const month = Number(dmyMatch[2]);
    const year = Number(dmyMatch[3]);
    if (month >= 1 && month <= 12 && day >= 1 && day <= 31 && year >= 1900) {
      return `${dmyMatch[3]}-${dmyMatch[2]}-${dmyMatch[1]}`;
    }
    return null;
  }

  return null;
}

export function mapInvoiceToFormValues(
  result: InvoiceExtraction
): InvoiceMappedFormValues {
  const mapped: InvoiceMappedFormValues = {};

  if (result.recipient_name !== null) {
    const name = result.recipient_name.trim();
    if (name) mapped.recipient_name = name;
  }

  if (result.recipient_bin !== null) {
    const bin = sanitizeDigits(result.recipient_bin);
    if (bin) mapped.recipient_bin = bin;
  }

  if (result.recipient_iik !== null) {
    const iik = sanitizeCode(result.recipient_iik);
    if (iik) mapped.recipient_iik = iik;
  }

  if (result.recipient_bik !== null) {
    const bik = sanitizeCode(result.recipient_bik);
    if (bik) mapped.recipient_bik = bik;
  }

  if (
    result.amount_kzt !== null &&
    Number.isFinite(result.amount_kzt) &&
    result.amount_kzt > 0
  ) {
    mapped.amount_kzt = String(result.amount_kzt);
  }

  if (result.purpose !== null) {
    const purpose = result.purpose.trim();
    if (purpose) mapped.purpose = purpose;
  }

  if (result.kbe !== null) {
    const kbe = sanitizeDigits(result.kbe).slice(0, 2);
    if (kbe) mapped.kbe = kbe;
  }

  if (result.knp !== null) {
    const knp = sanitizeDigits(result.knp).slice(0, 3);
    if (knp) mapped.knp = knp;
  }

  if (result.invoice_number !== null) {
    const docNumber = result.invoice_number.trim();
    if (docNumber) mapped.doc_number = docNumber;
  }

  if (result.invoice_date !== null) {
    const docDate = normalizeIsoDateForInput(result.invoice_date);
    if (docDate) mapped.doc_date = docDate;
  }

  return mapped;
}

/**
 * Applies only non-null mapped values to keys that actually exist on `prev`.
 */
export function applyMappedInvoiceValues<
  T extends Partial<Record<keyof InvoiceMappedFormValues, string>>,
>(
  prev: T,
  mapped: InvoiceMappedFormValues
): { next: T; updatedKeys: Array<keyof T> } {
  const next = { ...prev };
  const updatedKeys: Array<keyof T> = [];

  for (const key of Object.keys(mapped) as Array<keyof InvoiceMappedFormValues>) {
    const value = mapped[key];
    if (value !== undefined && key in prev) {
      const formKey = key as keyof T;
      (next as Record<keyof T, string>)[formKey] = value;
      updatedKeys.push(formKey);
    }
  }

  return { next, updatedKeys };
}

export interface ExtractInvoiceOptions {
  apiBase?: string | null;
  signal?: AbortSignal;
  lang?: Lang;
  timeoutMs?: number;
}

export async function extractInvoice(
  file: File,
  options: ExtractInvoiceOptions = {}
): Promise<InvoiceExtraction> {
  const lang = options.lang ?? getCurrentLang();
  const dict = getDictionary(lang);

  const validation = validateInvoiceFile(file, lang);
  if (!validation.ok) {
    throw new InvoiceExtractError({
      code: validation.code,
      status: 0,
      message: validation.message,
    });
  }

  const resolvedApiBase =
    options.apiBase !== undefined
      ? normalizeApiBase(options.apiBase)
      : getInvoiceApiBase();

  if (!resolvedApiBase) {
    throw new InvoiceExtractError({
      code: "missing_api_base",
      status: 0,
      message: dict.invoice.errors.apiBaseMissing,
    });
  }

  const externalSignal = options.signal;
  if (externalSignal?.aborted) {
    throw new DOMException("The operation was aborted.", "AbortError");
  }

  const controller = new AbortController();
  let timedOut = false;

  const onExternalAbort = () => {
    controller.abort();
  };
  externalSignal?.addEventListener("abort", onExternalAbort, { once: true });

  const timeoutMs = options.timeoutMs ?? INVOICE_EXTRACT_TIMEOUT_MS;
  const timeoutId = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);

  const filename = file.name?.trim() || "invoice";
  const url = `${resolvedApiBase}/api/invoice/extract?filename=${encodeURIComponent(filename)}`;
  const contentType =
    file.type && ALLOWED_MIME_SET.has(file.type.trim().toLowerCase())
      ? file.type.trim().toLowerCase()
      : validation.mimeType;

  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": contentType,
      },
      body: file,
      credentials: "omit",
      cache: "no-store",
      signal: controller.signal,
    });
  } catch (err) {
    if (timedOut) {
      throw new InvoiceExtractError({
        code: "timeout",
        status: 0,
        message: dict.invoice.errors.timeout,
      });
    }
    if (externalSignal?.aborted || isInvoiceExtractAbortError(err)) {
      throw err;
    }
    throw new InvoiceExtractError({
      code: "network",
      status: 0,
      message: dict.invoice.errors.network,
    });
  } finally {
    clearTimeout(timeoutId);
    externalSignal?.removeEventListener("abort", onExternalAbort);
  }

  let body: unknown = null;
  const responseContentType = response.headers.get("content-type") || "";
  if (responseContentType.includes("application/json")) {
    try {
      body = await response.json();
    } catch {
      body = null;
    }
  } else {
    try {
      const text = await response.text();
      if (text) {
        try {
          body = JSON.parse(text);
        } catch {
          body = text;
        }
      }
    } catch {
      body = null;
    }
  }

  if (!response.ok) {
    const detail =
      body && typeof body === "object" && "detail" in body
        ? (body as { detail: unknown }).detail
        : body;
    throw buildHttpError(response.status, detail, dict);
  }

  return parseInvoiceExtraction(body, lang);
}
