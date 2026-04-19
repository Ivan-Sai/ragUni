"use client";

import { useSession } from "next-auth/react";
import { redirect } from "next/navigation";
import { useTranslations } from "next-intl";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatsCards } from "@/components/admin/stats-cards";
import { PendingTeachers } from "@/components/admin/pending-teachers";
import { useAdminStats } from "@/hooks/use-admin-stats";
import { useAdminUsers } from "@/hooks/use-admin-users";
import { Skeleton } from "@/components/ui/skeleton";

export default function AdminDashboardPage() {
  const { data: session, status } = useSession();
  const t = useTranslations("admin.dashboard");
  const token = session?.accessToken || "";

  const { stats, isLoading: statsLoading, refresh: refreshStats } =
    useAdminStats({ token });
  const {
    pendingTeachers,
    isLoading: usersLoading,
    approveTeacher,
    rejectTeacher,
  } = useAdminUsers({ token });

  if (status === "unauthenticated") {
    redirect("/login");
  }

  if (status === "loading") {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <div className="grid gap-4 md:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      </div>
    );
  }

  if (session?.user?.role !== "admin") {
    redirect("/chat");
  }

  const totalChunks =
    stats.documentStats?.vector_store?.total_chunks ?? 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            {t("title")}
          </h1>
          <p className="text-muted-foreground">
            {t("description")}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={refreshStats}>
          <RefreshCw className="mr-2 h-4 w-4" />
          {t("refresh")}
        </Button>
      </div>

      <StatsCards
        totalUsers={stats.totalUsers}
        pendingTeachers={stats.pendingTeachers}
        totalDocuments={stats.documentStats?.documents.total ?? 0}
        totalChunks={totalChunks as number}
        isLoading={statsLoading}
      />

      <PendingTeachers
        teachers={pendingTeachers}
        onApprove={approveTeacher}
        onReject={rejectTeacher}
        isLoading={usersLoading}
      />
    </div>
  );
}
