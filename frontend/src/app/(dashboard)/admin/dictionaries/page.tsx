"use client";

import { useState } from "react";
import { useSession } from "next-auth/react";
import { redirect } from "next/navigation";
import { useTranslations } from "next-intl";

import { FacultySection } from "@/components/admin/dictionaries/faculty-section";
import { GroupSection } from "@/components/admin/dictionaries/group-section";

export default function AdminDictionariesPage() {
  const { data: session, status } = useSession();
  const t = useTranslations("admin.dictionaries");
  // Bumped on every faculty CRUD action so the group section's
  // dropdowns refresh against the latest list without a full page
  // reload.
  const [refreshKey, setRefreshKey] = useState(0);

  if (status === "loading") return null;
  if (status === "unauthenticated") {
    redirect("/login");
  }
  if (session?.user?.role !== "admin") {
    redirect("/chat");
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{t("title")}</h1>
        <p className="text-muted-foreground">{t("description")}</p>
      </div>

      <FacultySection onChanged={() => setRefreshKey((k) => k + 1)} />
      <GroupSection refreshKey={refreshKey} />
    </div>
  );
}
