import type { ReactNode } from "react";
import { InfoNavLinks } from "@/components/info/InfoNavLinks";
import { SiteFooter } from "@/components/info/SiteFooter";

/**
 * RootLayout already renders AppShell (or ProdShell) with AppHeader/ProdHeader and <main>.
 * This nested layout intentionally avoids duplicating the header or <main>, providing only
 * the info section navigation bar, content container, and footer.
 */
export default function InfoRouteGroupLayout({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <div className="space-y-6 pb-4 sm:space-y-8">
      <InfoNavLinks variant="bar" />
      <div className="space-y-6 sm:space-y-8">{children}</div>
      <SiteFooter embedded />
    </div>
  );
}
