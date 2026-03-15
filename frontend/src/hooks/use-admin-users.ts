"use client";

import { useState, useCallback, useEffect } from "react";
import { useTranslations } from "next-intl";
import { toast } from "sonner";
import { adminApi } from "@/lib/api";
import type { UserResponse, UserRole } from "@/types/api";

const PAGE_SIZE = 50;

interface UseAdminUsersOptions {
  token: string;
}

interface UseAdminUsersReturn {
  users: UserResponse[];
  total: number;
  pendingTeachers: UserResponse[];
  isLoading: boolean;
  error: string | null;
  hasMore: boolean;
  approveTeacher: (userId: string) => Promise<void>;
  rejectTeacher: (userId: string) => Promise<void>;
  blockUser: (userId: string, isActive: boolean) => Promise<void>;
  changeRole: (userId: string, role: UserRole) => Promise<void>;
  refresh: () => Promise<void>;
  loadMore: () => void;
}

export function useAdminUsers({
  token,
}: UseAdminUsersOptions): UseAdminUsersReturn {
  const t = useTranslations("admin.pending");
  const tCommon = useTranslations("common");
  const [users, setUsers] = useState<UserResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [pendingTeachers, setPendingTeachers] = useState<UserResponse[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchUsers = useCallback(
    async (pageNum: number, append: boolean) => {
      if (!token) return;

      setIsLoading(true);
      setError(null);

      try {
        const usersData = await adminApi.getUsers(
          token,
          pageNum * PAGE_SIZE,
          PAGE_SIZE
        );

        if (append) {
          setUsers((prev) => [...prev, ...usersData.users]);
        } else {
          setUsers(usersData.users);
        }
        setTotal(usersData.total);
        setHasMore(usersData.users.length >= PAGE_SIZE);
      } catch (err) {
        setError(err instanceof Error ? err.message : tCommon("unknownError"));
      } finally {
        setIsLoading(false);
      }
    },
    [token, tCommon]
  );

  const fetchAll = useCallback(async () => {
    if (!token) return;

    setPage(0);
    setIsLoading(true);
    setError(null);

    try {
      const [usersData, pendingData] = await Promise.all([
        adminApi.getUsers(token, 0, PAGE_SIZE),
        adminApi.getPendingTeachers(token),
      ]);
      setUsers(usersData.users);
      setTotal(usersData.total);
      setHasMore(usersData.users.length >= PAGE_SIZE);
      setPendingTeachers(pendingData);
    } catch (err) {
      setError(err instanceof Error ? err.message : tCommon("unknownError"));
    } finally {
      setIsLoading(false);
    }
  }, [token, tCommon]);

  const loadMore = useCallback(() => {
    const nextPage = page + 1;
    setPage(nextPage);
    fetchUsers(nextPage, true);
  }, [page, fetchUsers]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  const approveTeacher = useCallback(
    async (userId: string) => {
      await adminApi.approveTeacher(userId, token);
      setPendingTeachers((prev) => prev.filter((t) => t.id !== userId));
      setUsers((prev) =>
        prev.map((u) => (u.id === userId ? { ...u, is_approved: true } : u))
      );
      toast.success(t("approved"));
    },
    [token, t]
  );

  const rejectTeacher = useCallback(
    async (userId: string) => {
      await adminApi.rejectTeacher(userId, token);
      setPendingTeachers((prev) => prev.filter((t) => t.id !== userId));
      setUsers((prev) => prev.filter((u) => u.id !== userId));
      setTotal((prev) => prev - 1);
      toast.success(t("rejected"));
    },
    [token, t]
  );

  const blockUser = useCallback(
    async (userId: string, isActive: boolean) => {
      await adminApi.blockUser(userId, isActive, token);
      setUsers((prev) =>
        prev.map((u) => (u.id === userId ? { ...u, is_active: isActive } : u))
      );
      toast.success(isActive ? t("userUnblocked") : t("userBlocked"));
    },
    [token, t]
  );

  const changeRole = useCallback(
    async (userId: string, role: UserRole) => {
      await adminApi.changeRole(userId, role, token);
      setUsers((prev) =>
        prev.map((u) => (u.id === userId ? { ...u, role } : u))
      );
      toast.success(t("roleChanged"));
    },
    [token, t]
  );

  return {
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
    refresh: fetchAll,
    loadMore,
  };
}
