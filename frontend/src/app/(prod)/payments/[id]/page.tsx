"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { AlertTriangle, ArrowLeft, RefreshCw } from "lucide-react";
import { PaymentDetail } from "@/components/prod/PaymentDetail";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useT } from "@/i18n";
import { ApiError, getPayment, getProdErrorMessage } from "@/lib/prod/api";
import type { Payment } from "@/lib/prod/types";
import { cn } from "cn";

export default function ProdPaymentDetailPage() {
  const params = useParams<{ id: string }>();
  const paymentId = typeof params?.id === "string" ? params.id : "";
  const { t, lang } = useT();

  const fetchKey = `${paymentId}|${lang}`;
  const [loadState, setLoadState] = useState<{
    key: string;
    payment: Payment | null;
    notFound: boolean;
    error: string | null;
  } | null>(null);

  const reloadPayment = useCallback(async () => {
    if (!paymentId) return;
    try {
      const data = await getPayment(paymentId, lang);
      setLoadState({
        key: fetchKey,
        payment: data,
        notFound: false,
        error: null,
      });
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setLoadState({
          key: fetchKey,
          payment: null,
          notFound: true,
          error: null,
        });
      } else {
        setLoadState((prev) => ({
          key: fetchKey,
          payment: prev?.payment ?? null,
          notFound: false,
          error: getProdErrorMessage(err),
        }));
      }
    }
  }, [fetchKey, lang, paymentId]);

  useEffect(() => {
    if (!paymentId) return;
    const controller = new AbortController();

    getPayment(paymentId, lang, { signal: controller.signal })
      .then((data) => {
        setLoadState({
          key: fetchKey,
          payment: data,
          notFound: false,
          error: null,
        });
      })
      .catch((err) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        if (err instanceof ApiError && err.status === 404) {
          setLoadState({
            key: fetchKey,
            payment: null,
            notFound: true,
            error: null,
          });
        } else {
          setLoadState((prev) => ({
            key: fetchKey,
            payment: prev?.payment ?? null,
            notFound: false,
            error: getProdErrorMessage(err),
          }));
        }
      });

    return () => controller.abort();
  }, [fetchKey, lang, paymentId]);

  const payment = loadState?.payment ?? null;
  const notFoundError = Boolean(loadState?.notFound);
  const error = loadState?.error ?? null;
  const isLoading = loadState === null || loadState.key !== fetchKey;

  if (isLoading && !payment) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between gap-3">
          <Skeleton className="h-8 w-36 rounded-[6px]" />
          <Skeleton className="h-8 w-32 rounded-[6px]" />
        </div>
        <Skeleton className="h-36 w-full rounded-[8px]" />
        <Skeleton className="h-16 w-full rounded-[8px]" />
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
          <Skeleton className="h-72 w-full rounded-[8px]" />
          <Skeleton className="h-56 w-full rounded-[8px]" />
        </div>
      </div>
    );
  }

  if (notFoundError) {
    return (
      <div className="space-y-4">
        <Link
          href="/payments"
          className={cn(
            buttonVariants({ variant: "ghost", size: "sm" }),
            "min-h-11 gap-1.5 text-muted-foreground hover:text-foreground sm:min-h-8"
          )}
        >
          <ArrowLeft className="size-4" />
          <span>{t.prod.detail.backToPayments}</span>
        </Link>

        <div className="ui-panel">
          <div className="ui-empty">
            <div className="ui-empty-title">{t.prod.detail.notFoundTitle}</div>
            <p className="ui-empty-desc">
              {t.prod.detail.notFoundDescription}
            </p>
            <Link
              href="/payments"
              className={cn(
                buttonVariants({ variant: "outline", size: "sm" }),
                "mt-2 min-h-10 gap-1.5 sm:min-h-8"
              )}
            >
              <ArrowLeft className="size-3.5" />
              <span>{t.prod.detail.backToPayments}</span>
            </Link>
          </div>
        </div>
      </div>
    );
  }

  if (error && !payment) {
    return (
      <div className="space-y-4">
        <Link
          href="/payments"
          className={cn(
            buttonVariants({ variant: "ghost", size: "sm" }),
            "min-h-11 gap-1.5 text-muted-foreground hover:text-foreground sm:min-h-8"
          )}
        >
          <ArrowLeft className="size-4" />
          <span>{t.prod.detail.backToPayments}</span>
        </Link>

        <Alert variant="destructive" className="ui-notice ui-notice-danger">
          <AlertTriangle className="size-4" />
          <AlertTitle>{t.common.serverErrorTitle}</AlertTitle>
          <AlertDescription className="flex flex-wrap items-center justify-between gap-2 break-words">
            <span>{error}</span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void reloadPayment()}
              className="min-h-10 gap-1.5 sm:min-h-8"
            >
              <RefreshCw className="size-3.5" />
              <span>{t.common.retry}</span>
            </Button>
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  if (!payment) return null;

  return (
    <PaymentDetail
      payment={payment}
      onPaymentUpdated={(updated) =>
        setLoadState({
          key: fetchKey,
          payment: updated,
          notFound: false,
          error: null,
        })
      }
      onReloadPayment={reloadPayment}
    />
  );
}
