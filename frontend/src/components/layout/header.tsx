"use client";

import Link from "next/link";
import { useSession, signOut } from "next-auth/react";
import { useTranslations } from "next-intl";
import { LogOut } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/layout/theme-toggle";

export function Header() {
  const t = useTranslations("layout.header");
  const { data: session, status } = useSession();

  return (
    <header className="flex h-14 items-center justify-between border-b px-4">
      <h1 className="text-lg font-semibold">UniRAG</h1>

      <div className="flex items-center gap-3">
        <ThemeToggle />

        {status === "authenticated" && session?.user ? (
          <div className="flex items-center gap-3">
            <div className="text-sm text-right">
              <p className="font-medium">{session.user.name}</p>
              <p className="text-muted-foreground text-xs">
                {session.user.role}
              </p>
            </div>
            <Button
              variant="ghost"
              size="icon"
              aria-label={t("logout")}
              onClick={() => signOut({ callbackUrl: "/login" })}
            >
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        ) : (
          <Link
            href="/login"
            className="text-sm font-medium hover:underline"
          >
            {t("login")}
          </Link>
        )}
      </div>
    </header>
  );
}
