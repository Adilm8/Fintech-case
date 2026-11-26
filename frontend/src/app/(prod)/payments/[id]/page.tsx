"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { AlertTriangle, ArrowLeft, Inbox, RefreshCw } from "lucide-react";
import { PaymentDetail } from "@/components/prod/PaymentDetail";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
      <div className="space-y-5">
        <div className="flex items-center justify-between gap-3">
          <Skeleton className="h-9 w-36 rounded-lg" />
          <Skeleton className="h-9 w-32 rounded-lg" />
        </div>
        <Skeleton className="h-36 w-full rounded-xl" />
        <Skeleton className="h-20 w-full rounded-xl" />
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">
          <Skeleton className="h-72 w-full rounded-xl" />
          <Skeleton className="h-56 w-full rounded-xl" />
        </div>
      </div>
    );
  }

  if (notFoundError) {
    return (
      <div className="space-y-5">
        <Link
          href="/payments"
          className={cn(
            buttonVariants({ variant: "ghost", size: "sm" }),
            "min-h-11 gap-1.5 text-muted-foreground hover:text-foreground sm:min-h-9"
          )}
        >
          <ArrowLeft className="size-4" />
          <span>{t.prod.detail.backToPayments}</span>
        </Link>

        <Card>
          <CardContent className="flex flex-col items-center justify-center gap-3 py-16 px-4 text-center">
            <div className="flex size-12 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
              <Inbox className="size-6" />
            </div>
            <div className="space-y-1">
              <div className="text-base font-semibold text-foreground">
                {t.prod.detail.notFoundTitle}
              </div>
              <p className="max-w-md text-sm text-muted-foreground">
                {t.prod.detail.notFoundDescription}
              </p>
            </div>
            <Link
              href="/payments"
              className={cn(
                buttonVariants({ variant: "outline" }),
                "mt-1 min-h-11 gap-2 rounded-xl sm:min-h-9"
              )}
            >
              <ArrowLeft className="size-4" />
              <span>{t.prod.detail.backToPayments}</span>
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (error && !payment) {
    return (
      <div className="space-y-5">
        <Link
          href="/payments"
          className={cn(
            buttonVariants({ variant: "ghost", size: "sm" }),
            "min-h-11 gap-1.5 text-muted-foreground hover:text-foreground sm:min-h-9"
          )}
        >
          <ArrowLeft className="size-4" />
          <span>{t.prod.detail.backToPayments}</span>
        </Link>

        <Alert
          variant="destructive"
          className="rounded-2xl border-red-300 bg-red-50/90"
        >
          <AlertTriangle className="size-4" />
          <AlertTitle>{t.common.serverErrorTitle}</AlertTitle>
          <AlertDescription className="flex flex-wrap items-center justify-between gap-2 break-words">
            <span>{error}</span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void reloadPayment()}
              className="gap-1.5 border-red-300 bg-white text-red-900 hover:bg-red-50"
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
