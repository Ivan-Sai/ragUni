"use client";

import { useSession } from "next-auth/react";
import { useTranslations } from "next-intl";
import { Filter } from "lucide-react";

/**
 * Inline pill that tells the student which audience filter is being
 * applied to their queries. Renders only when the user is a student
 * with at least a faculty + group set — teachers/admins see every
 * document irrespective of profile, so the banner would be a lie.
 */
export function PersonalizationBanner() {
  const { data: session } = useSession();
  const t = useTranslations("chat.personalization");
  const tDict = useTranslations("admin.dictionaries");
  const user = session?.user;

  if (!user) return null;
  if (user.role !== "student") return null;
  if (!user.faculty_name || !user.group_name) return null;

  const facets = [user.group_name, user.faculty_name];
  if (user.year) facets.push(t("yearShort", { year: user.year }));
  if (user.level) facets.push(tDict(`level.${user.level}`));

  return (
    <div className="border-b bg-muted/30 px-4 py-1.5 text-xs text-muted-foreground">
      <div className="flex items-center gap-2">
        <Filter className="h-3 w-3" />
        <span className="font-medium">{t("title")}</span>
        <span>{facets.join(" · ")}</span>
      </div>
    </div>
  );
}
