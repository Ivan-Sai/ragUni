"use client";

import { useSession } from "next-auth/react";
import { redirect } from "next/navigation";
import { useTranslations } from "next-intl";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { UsersTable } from "@/components/admin/users-table";
import { PendingTeachers } from "@/components/admin/pending-teachers";
import { useAdminUsers } from "@/hooks/use-admin-users";

export default function AdminUsersPage() {
  const { data: session } = useSession();

  if (session?.user?.role !== "admin") {
    redirect("/chat");
  }

  const t = useTranslations("admin.users");
  const token = session?.accessToken || "";

  const {
    users,
    total,
    pendingTeachers,
    isLoading,
    error,
    hasMore,
    approveTeacher,
    rejectTeacher,
    blockUser,
    changeRole,
    refresh,
    loadMore,
  } = useAdminUsers({ token });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            {t("title")}
          </h1>
          <p className="text-muted-foreground">
            {t("totalCount", { count: total })}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={refresh}>
          <RefreshCw className="mr-2 h-4 w-4" />
          {t("refresh")}
        </Button>
      </div>

      {error && (
        <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      <PendingTeachers
        teachers={pendingTeachers}
        onApprove={approveTeacher}
        onReject={rejectTeacher}
        isLoading={isLoading}
      />

      <UsersTable
        users={users}
        isLoading={isLoading}
        hasMore={hasMore}
        onBlock={blockUser}
        onChangeRole={changeRole}
        onLoadMore={loadMore}
      />
    </div>
  );
}
