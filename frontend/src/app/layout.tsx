import type { Metadata, Viewport } from "next";
import { AppShell } from "@/components/AppShell";
import { ProdShell } from "@/components/prod/ProdShell";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { LangProvider } from "@/i18n";
import { ru } from "@/i18n/ru";
import { IS_PROD } from "@/lib/mode";
import "./globals.css";

export const metadata: Metadata = {
  title: ru.brand.name,
  description: ru.brand.metaDescription,
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="ru"
      className="h-full antialiased"
      suppressHydrationWarning
    >
      <body className="min-h-full flex flex-col bg-background text-foreground">
        <LangProvider>
          <TooltipProvider>
            {IS_PROD ? (
              <ProdShell>{children}</ProdShell>
            ) : (
              <AppShell>{children}</AppShell>
            )}
            <Toaster />
          </TooltipProvider>
        </LangProvider>
      </body>
    </html>
  );
}
