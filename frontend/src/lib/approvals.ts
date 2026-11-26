import type { Approval, ApprovalStatus, CheckRequest } from "./types";

export const MIN_DIRECTOR_COMMENT_LENGTH = 10;

export const APPROVAL_STATUS_STYLES: Record<
  ApprovalStatus,
  {
    badgeClass: string;
    bannerClass: string;
  }
> = {
  pending: {
    badgeClass: "border-amber-300/80 bg-amber-50 text-amber-900",
    bannerClass: "border-amber-300 bg-amber-50/90 text-amber-950",
  },
  approved: {
    badgeClass: "border-[#00AB75]/35 bg-[#E8F8F2] text-[#006B49]",
    bannerClass: "border-[#00AB75]/35 bg-[#E8F8F2] text-[#064A34]",
  },
  rejected: {
    badgeClass: "border-red-300/80 bg-red-50 text-red-800",
    bannerClass: "border-red-300 bg-red-50/90 text-red-950",
  },
};

function normalizeBin(value: string | null | undefined): string {
  return (value ?? "").replace(/\s+/g, "");
}

function normalizeIik(value: string | null | undefined): string {
  return (value ?? "").replace(/\s+/g, "").toUpperCase();
}

function parseAmount(value: number | string | null | undefined): number | null {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }
  if (typeof value === "string") {
    const cleaned = value.replace(/[^\d.,-]/g, "").replace(",", ".");
    if (!cleaned) return null;
    const num = Number(cleaned);
    return Number.isFinite(num) ? num : null;
  }
  return null;
}

function extractApprovalPaymentKey(approval: Approval): {
  bin: string;
  iik: string;
  amount: number | null;
} {
  if (approval.request) {
    return {
      bin: normalizeBin(approval.request.recipient_bin),
      iik: normalizeIik(approval.request.recipient_iik),
      amount: parseAmount(approval.request.amount_kzt),
    };
  }

  const comparison = approval.check?.comparison ?? [];
  const binRow = comparison.find((row) => row.field === "bin");
  const iikRow = comparison.find((row) => row.field === "iik");
  const amountRow = comparison.find((row) => row.field === "amount");

  return {
    bin: normalizeBin(binRow?.in_invoice),
    iik: normalizeIik(iikRow?.in_invoice),
    amount: parseAmount(amountRow?.in_invoice),
  };
}

function parseTimestamp(value: string | null | undefined): number | null {
  if (!value) return null;
  const ms = Date.parse(value);
  return Number.isNaN(ms) ? null : ms;
}

function getApprovalOrderTimestamp(approval: Approval): number | null {
  const created = parseTimestamp(approval.created_at);
  const decided = parseTimestamp(approval.decided_at);
  if (created !== null && decided !== null) {
    return Math.max(created, decided);
  }
  return decided ?? created;
}

export function findApprovalForPayment(
  approvals: Approval[],
  payment: Pick<CheckRequest, "recipient_bin" | "recipient_iik" | "amount_kzt">
): Approval | null {
  const targetBin = normalizeBin(payment.recipient_bin);
  const targetIik = normalizeIik(payment.recipient_iik);
  const targetAmount = parseAmount(payment.amount_kzt);

  if (!targetBin || !targetIik || targetAmount === null) {
    return null;
  }

  let best: Approval | null = null;
  let bestTime: number | null = null;
  let bestIndex = -1;

  approvals.forEach((approval, index) => {
    const key = extractApprovalPaymentKey(approval);
    if (
      key.bin !== targetBin ||
      key.iik !== targetIik ||
      key.amount === null ||
      Math.abs(key.amount - targetAmount) >= 0.01
    ) {
      return;
    }

    const ts = getApprovalOrderTimestamp(approval);
    if (best === null) {
      best = approval;
      bestTime = ts;
      bestIndex = index;
      return;
    }

    if (ts !== null && bestTime !== null) {
      if (ts > bestTime || (ts === bestTime && index > bestIndex)) {
        best = approval;
        bestTime = ts;
        bestIndex = index;
      }
      return;
    }

    if (ts !== null && bestTime === null) {
      if (approval.status !== "pending" || index > bestIndex) {
        best = approval;
        bestTime = ts;
        bestIndex = index;
      }
      return;
    }

    if (index > bestIndex) {
      best = approval;
      bestTime = ts;
      bestIndex = index;
    }
  });

  return best;
}

export function canTrustApproval(approval: Approval): boolean {
  if (approval.check?.verdict !== "yellow") {
    return false;
  }
  const signals = approval.check?.signals ?? [];
  const hasBlock = signals.some((signal) => signal.severity === "block");
  if (hasBlock) {
    return false;
  }
  return signals.some(
    (signal) =>
      signal.rule_id === "iik_changed" || signal.rule_id === "bank_changed"
  );
}
