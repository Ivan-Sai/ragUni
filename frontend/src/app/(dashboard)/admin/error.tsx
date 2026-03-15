"use client";

import { useEffect } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";

export default function AdminError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const t = useTranslations("errors.admin");

  useEffect(() => {
    console.error("Admin error:", error);
  }, [error]);

  return (
    <div className="flex flex-1 items-center justify-center p-8">
      <div className="text-center space-y-4 max-w-md">
        <h2 className="text-xl font-semibold">{t("title")}</h2>
        <p className="text-muted-foreground">
          {t("description")}
        </p>
        <Button onClick={reset} variant="outline">
          {t("retry")}
        </Button>
      </div>
    </div>
  );
}
