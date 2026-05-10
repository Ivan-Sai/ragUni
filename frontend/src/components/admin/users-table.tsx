"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { Ban, Pencil, ShieldCheck } from "lucide-react";
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
import { AdminUserEditDialog } from "@/components/admin/admin-user-edit-dialog";

interface UsersTableProps {
  users: UserResponse[];
  isLoading: boolean;
  hasMore?: boolean;
  onBlock: (userId: string, isActive: boolean) => Promise<void>;
  onChangeRole: (userId: string, role: UserRole) => Promise<void>;
  onUserUpdated?: () => void;
  onLoadMore?: () => void;
}

function formatDate(dateString: string, locale: string): string {
  // Locale comes from useLocale() so an English admin sees English
  // months. Hardcoding "uk-UA" used to render Ukrainian dates for
  // every user regardless of UI language.
  return new Date(dateString).toLocaleDateString(locale, {
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
  onUserUpdated,
  onLoadMore,
}: UsersTableProps) {
  const t = useTranslations("admin.users");
  const locale = useLocale();
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);
  const [editingUser, setEditingUser] = useState<UserResponse | null>(null);

  // Same Base UI Select trick for the role column — without an
  // items map the trigger shows "student" instead of "Студент".
  const roleLabels: Record<string, string> = {
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
              <TableHead>{t("group")}</TableHead>
              <TableHead>{t("status")}</TableHead>
              <TableHead>{t("registrationDate")}</TableHead>
              <TableHead className="text-right">{t("actions")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {users.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8} className="text-center text-muted-foreground">
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
                      items={roleLabels}
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
                  <TableCell>{user.faculty_name || t("noFaculty")}</TableCell>
                  <TableCell>
                    {user.group_name ? (
                      <span>
                        {user.group_name}
                        {user.year && (
                          <span className="ml-1 text-xs text-muted-foreground">
                            · {user.year}
                          </span>
                        )}
                      </span>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TableCell>
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
                  <TableCell>{formatDate(user.created_at, locale)}</TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setEditingUser(user)}
                        disabled={actionInProgress === user.id}
                      >
                        <Pencil className="h-4 w-4" />
                      </Button>
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
                    </div>
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

      <AdminUserEditDialog
        user={editingUser}
        onClose={() => setEditingUser(null)}
        onSaved={() => {
          setEditingUser(null);
          onUserUpdated?.();
        }}
      />
    </div>
  );
}
