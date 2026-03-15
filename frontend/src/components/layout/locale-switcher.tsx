"use client";

import { useLocale } from "next-intl";
import { useRouter } from "next/navigation";
import { useTransition } from "react";
import { Button } from "@/components/ui/button";
import { type Locale, locales } from "@/i18n/config";

const localeLabels: Record<Locale, string> = {
  en: "EN",
  uk: "UK",
};

export function LocaleSwitcher() {
  const locale = useLocale() as Locale;
  const router = useRouter();
  const [isPending, startTransition] = useTransition();

  function switchLocale() {
    const nextLocale = locales.find((l) => l !== locale) ?? locales[0];
    startTransition(() => {
      document.cookie = `locale=${nextLocale};path=/;max-age=31536000`;
      router.refresh();
    });
  }

  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={switchLocale}
      disabled={isPending}
      aria-label="Switch language"
    >
      {localeLabels[locale]}
    </Button>
  );
}
