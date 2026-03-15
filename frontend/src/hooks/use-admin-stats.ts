"use client";

import { useState, useCallback, useEffect } from "react";
import { useTranslations } from "next-intl";
import { adminApi, documentsApi } from "@/lib/api";
import type { DocumentStats, SystemHealth } from "@/types/api";

interface UseAdminStatsOptions {
  token: string;
}

interface AdminStats {
  totalUsers: number;
  pendingTeachers: number;
  documentStats: DocumentStats | null;
  systemHealth: SystemHealth | null;
}

interface UseAdminStatsReturn {
  stats: AdminStats;
  isLoading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

export function useAdminStats({
  token,
}: UseAdminStatsOptions): UseAdminStatsReturn {
  const t = useTranslations("admin.stats");
  const tCommon = useTranslations("common");
  const [stats, setStats] = useState<AdminStats>({
    totalUsers: 0,
    pendingTeachers: 0,
    documentStats: null,
    systemHealth: null,
  });
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchStats = useCallback(async () => {
    if (!token) return;

    setIsLoading(true);
    setError(null);

    try {
      const [usersData, pendingData, docStats, health] =
        await Promise.allSettled([
          adminApi.getUsers(token, 0, 1),
          adminApi.getPendingTeachers(token),
          documentsApi.getStats(token),
          documentsApi.getHealth(token),
        ]);

      const failures = [usersData, pendingData, docStats, health]
        .filter((r) => r.status === "rejected")
        .map((r) => (r as PromiseRejectedResult).reason);

      setStats({
        totalUsers:
          usersData.status === "fulfilled" ? usersData.value.total : 0,
        pendingTeachers:
          pendingData.status === "fulfilled" ? pendingData.value.length : 0,
        documentStats:
          docStats.status === "fulfilled" ? docStats.value : null,
        systemHealth: health.status === "fulfilled" ? health.value : null,
      });

      if (failures.length > 0) {
        const msg = failures[0] instanceof Error ? failures[0].message : t("loadError");
        setError(msg);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : tCommon("unknownError"));
    } finally {
      setIsLoading(false);
    }
  }, [token, t, tCommon]);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  return {
    stats,
    isLoading,
    error,
    refresh: fetchStats,
  };
}
