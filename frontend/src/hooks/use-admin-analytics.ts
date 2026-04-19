"use client";

import { useState, useEffect, useCallback } from "react";
import { adminApi } from "@/lib/api";

interface DayCount {
  date: string;
  count: number;
}

interface AnalyticsData {
  total_queries: number;
  total_logins: number;
  total_uploads: number;
  queries_per_day: DayCount[];
  active_users_per_day: DayCount[];
  avg_response_time: number | null;
}

interface UseAdminAnalyticsProps {
  token: string;
  days?: number;
}

export function useAdminAnalytics({ token, days = 30 }: UseAdminAnalyticsProps) {
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAnalytics = useCallback(async () => {
    if (!token) return;
    setIsLoading(true);
    setError(null);
    try {
      const result = await adminApi.getAnalytics(token, days);
      setData(result);
    } catch {
      setError("analytics_load_error");
    } finally {
      setIsLoading(false);
    }
  }, [token, days]);

  useEffect(() => {
    fetchAnalytics();
  }, [fetchAnalytics]);

  return { data, isLoading, error, refresh: fetchAnalytics };
}
