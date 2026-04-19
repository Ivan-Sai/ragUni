import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { AuthSessionProvider } from "@/components/providers/session-provider";
import { SessionGuard } from "@/components/providers/session-guard";
import { ThemeProvider } from "@/components/providers/theme-provider";
import { SentryProvider } from "@/components/providers/sentry-provider";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ErrorBoundary } from "@/components/error-boundary";
import { Toaster } from "sonner";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getMessages } from "next-intl/server";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin", "cyrillic"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains",
  subsets: ["latin", "cyrillic"],
});

export const metadata: Metadata = {
  title: "UniRAG — University Knowledge Base",
  description: "Intelligent RAG-based knowledge system for universities",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const locale = await getLocale();
  const messages = await getMessages();

  return (
    <html lang={locale} suppressHydrationWarning>
      <body
        className={`${inter.variable} ${jetbrainsMono.variable} antialiased`}
      >
        <SentryProvider>
          <AuthSessionProvider>
            <SessionGuard>
              <NextIntlClientProvider messages={messages}>
                <ThemeProvider>
                  <ErrorBoundary>
                    <TooltipProvider>{children}</TooltipProvider>
                  </ErrorBoundary>
                  <Toaster richColors position="top-right" />
                </ThemeProvider>
              </NextIntlClientProvider>
            </SessionGuard>
          </AuthSessionProvider>
        </SentryProvider>
      </body>
    </html>
  );
}
