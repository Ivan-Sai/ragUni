"use client";

import { useState, useCallback, useEffect } from "react";
import { useTranslations } from "next-intl";
import { chatApi } from "@/lib/api";
import type { ChatSessionPreview } from "@/types/api";

interface UseChatHistoryOptions {
  token: string;
}

interface UseChatHistoryReturn {
  sessions: ChatSessionPreview[];
  isLoading: boolean;
  error: string | null;
  deleteSession: (sessionId: string) => Promise<void>;
  refresh: () => Promise<void>;
}

export function useChatHistory({ token }: UseChatHistoryOptions): UseChatHistoryReturn {
  const t = useTranslations("common");
  const [sessions, setSessions] = useState<ChatSessionPreview[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchSessions = useCallback(async () => {
    if (!token) return;

    setIsLoading(true);
    setError(null);

    try {
      const data = await chatApi.getHistory(token);
      setSessions(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("unknownError"));
    } finally {
      setIsLoading(false);
    }
  }, [token, t]);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  const deleteSession = useCallback(
    async (sessionId: string) => {
      await chatApi.deleteSession(sessionId, token);
      setSessions((prev) => prev.filter((s) => s.session_id !== sessionId));
    },
    [token]
  );

  const refresh = useCallback(async () => {
    await fetchSessions();
  }, [fetchSessions]);

  return {
    sessions,
    isLoading,
    error,
    deleteSession,
    refresh,
  };
}
