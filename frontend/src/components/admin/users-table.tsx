"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Ban, ShieldCheck, MoreHorizontal } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import type { UserResponse, UserRole } from "@/types/api";

interface UsersTableProps {
  users: UserResponse[];
  isLoading: boolean;
  hasMore?: boolean;
  onBlock: (userId: string, isActive: boolean) => Promise<void>;
  onChangeRole: (userId: string, role: UserRole) => Promise<void>;
  onLoadMore?: () => void;
}

const roleBadgeVariant: Record<UserRole, "default" | "secondary" | "outline"> = {
  admin: "default",
  teacher: "secondary",
  student: "outline",
};

function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString("uk-UA", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

export function UsersTable({
  users,
  isLoading,
  hasMore,
  onBlock,
  onChangeRole,
  onLoadMore,
}: UsersTableProps) {
  const t = useTranslations("admin.users");
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);

  const roleLabels: Record<UserRole, string> = {
    admin: t("roleAdmin"),
    teacher: t("roleTeacher"),
    student: t("roleStudent"),
  };

  async function handleBlock(userId: string, isActive: boolean) {
    setActionInProgress(userId);
    try {
      await onBlock(userId, isActive);
    } finally {
      setActionInProgress(null);
    }
  }

  async function handleRoleChange(userId: string, role: UserRole) {
    setActionInProgress(userId);
    try {
      await onChangeRole(userId, role);
    } finally {
      setActionInProgress(null);
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-4">
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t("name")}</TableHead>
            <TableHead>{t("email")}</TableHead>
            <TableHead>{t("role")}</TableHead>
            <TableHead>{t("faculty")}</TableHead>
            <TableHead>{t("status")}</TableHead>
            <TableHead>{t("registrationDate")}</TableHead>
            <TableHead className="text-right">{t("actions")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {users.length === 0 ? (
            <TableRow>
              <TableCell colSpan={7} className="text-center text-muted-foreground">
                {t("empty")}
              </TableCell>
            </TableRow>
          ) : (
            users.map((user) => (
              <TableRow key={user.id}>
                <TableCell className="font-medium">{user.full_name}</TableCell>
                <TableCell>{user.email}</TableCell>
                <TableCell>
                  <Select
                    value={user.role}
                    onValueChange={(value) => {
                      if (value) handleRoleChange(user.id, value as UserRole);
                    }}
                    disabled={actionInProgress === user.id}
                  >
                    <SelectTrigger className="w-[120px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="student">{t("roleStudent")}</SelectItem>
                      <SelectItem value="teacher">{t("roleTeacher")}</SelectItem>
                      <SelectItem value="admin">{t("roleAdmin")}</SelectItem>
                    </SelectContent>
                  </Select>
                </TableCell>
                <TableCell>{user.faculty || t("noFaculty")}</TableCell>
                <TableCell>
                  <div className="flex gap-1">
                    <Badge
                      variant={user.is_active ? "outline" : "destructive"}
                    >
                      {user.is_active ? t("active") : t("blocked")}
                    </Badge>
                    {!user.is_approved && (
                      <Badge variant="secondary">{t("notApproved")}</Badge>
                    )}
                  </div>
                </TableCell>
                <TableCell>{formatDate(user.created_at)}</TableCell>
                <TableCell className="text-right">
                  <AlertDialog>
                    <AlertDialogTrigger
                      disabled={actionInProgress === user.id}
                      render={<Button variant="ghost" size="sm" />}
                    >
                      {user.is_active ? (
                        <Ban className="h-4 w-4 text-red-500" />
                      ) : (
                        <ShieldCheck className="h-4 w-4 text-green-500" />
                      )}
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>
                          {user.is_active
                            ? t("blockTitle")
                            : t("unblockTitle")}
                        </AlertDialogTitle>
                        <AlertDialogDescription>
                          {user.is_active
                            ? t("blockDescription", { name: user.full_name })
                            : t("unblockDescription", { name: user.full_name })}
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>{t("cancel")}</AlertDialogCancel>
                        <AlertDialogAction
                          onClick={() =>
                            handleBlock(user.id, !user.is_active)
                          }
                        >
                          {user.is_active ? t("block") : t("unblock")}
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>

    {hasMore && onLoadMore && (
      <div className="flex justify-center">
        <Button
          variant="outline"
          onClick={onLoadMore}
          disabled={isLoading}
        >
          {isLoading ? t("loading") : t("loadMore")}
        </Button>
      </div>
    )}
    </div>
  );
}
