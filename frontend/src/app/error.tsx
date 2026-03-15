"use client";

import { useEffect } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const t = useTranslations("errors.global");

  useEffect(() => {
    console.error("Application error:", error);
  }, [error]);

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="text-center space-y-4 max-w-md px-4">
        <h2 className="text-2xl font-bold">{t("title")}</h2>
        <p className="text-muted-foreground">
          {t("description")}
        </p>
        <Button onClick={reset}>{t("retry")}</Button>
      </div>
    </div>
  );
}
