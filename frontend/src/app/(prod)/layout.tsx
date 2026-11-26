import type { ReactNode } from "react";
import { notFound } from "next/navigation";
import { IS_PROD } from "@/lib/mode";

export default function ProdRouteGroupLayout({
  children,
}: {
  children: ReactNode;
}) {
  if (!IS_PROD) {
    notFound();
  }
  return <>{children}</>;
}
