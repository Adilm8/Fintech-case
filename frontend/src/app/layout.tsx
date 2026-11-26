import type { Metadata } from "next";
import { TooltipProvider } from "@/components/ui/tooltip";
import "./globals.css";

export const metadata: Metadata = {
  title: "BCC Business Shield",
  description: "Проверка платежей поставщикам перед подписанием",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ru" className="h-full antialiased">
      <body className="min-h-full flex flex-col">
        <TooltipProvider>{children}</TooltipProvider>
      </body>
    </html>
  );
}
