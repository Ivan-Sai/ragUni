"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { useTranslations } from "next-intl";
import { chatApi } from "@/lib/api";
import type { ChatMessage, ChatSource } from "@/types/api";

const MAX_QUESTION_LENGTH = 5000;
const SSE_TIMEOUT_MS = 90_000;
const TOKEN_BATCH_MS = 50;

interface UseChatOptions {
  token: string;
  sessionId?: string | null;
}

interface UseChatReturn {
  messages: ChatMessage[];
  isLoading: boolean;
  error: string | null;
  sessionId: string | null;
  sendMessage: (content: string) => Promise<void>;
  clearMessages: () => void;
}

async function parseSSEStream(
  stream: ReadableStream<Uint8Array>,
  onToken: (token: string) => void,
  onSources: (sources: ChatSource[]) => void,
  onSessionId: (id: string) => void,
  onError: (message: string) => void,
  fallbackErrorMessage: string
): Promise<void> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      let currentEvent = "";

      for (const line of lines) {
        if (line.startsWith("event: ")) {
          currentEvent = line.slice(7).trim();
        } else if (line.startsWith("data: ")) {
          const rawData = line.slice(6);
          try {
            const data = JSON.parse(rawData);

            switch (currentEvent) {
              case "token":
                onToken(data);
                break;
              case "sources":
                onSources(Array.isArray(data) ? data : []);
                break;
              case "session_id":
                onSessionId(data);
                break;
              case "error":
                onError(typeof data === "string" ? data : data.message || fallbackErrorMessage);
                break;
              case "done":
                break;
            }
          } catch {
            // skip malformed data
          }
          currentEvent = "";
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

function isNetworkError(err: unknown): boolean {
  if (err instanceof TypeError && /failed to fetch|networkerror|load failed/i.test(err.message.replace(/\s/g, ""))) return true;
  if (err instanceof DOMException && err.name === "AbortError") return false;
  if (err instanceof Error && /ECONNRESET|ECONNREFUSED|ETIMEDOUT|ERR_NETWORK/i.test(err.message)) return true;
  return false;
}

const MAX_RETRIES = 1;

export function useChat({ token, sessionId: initialSessionId = null }: UseChatOptions): UseChatReturn {
  const t = useTranslations("chat.errors");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(initialSessionId);

  // Mirror sessionId into a ref so stable callbacks below can read the
  // latest value without being re-created on every id change. Updating
  // the ref from an effect (not inline in render) satisfies React 19's
  // rules-of-refs lint: refs must only be mutated outside render.
  const sessionIdRef = useRef(sessionId);
  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  const abortControllerRef = useRef<AbortController | null>(null);

  // Load existing session with AbortController
  useEffect(() => {
    if (!initialSessionId || !token) return;

    const abortController = new AbortController();

    async function loadSession() {
      try {
        const session = await chatApi.getSession(initialSessionId!, token);
        if (!abortController.signal.aborted) {
          setMessages(session.messages);
          setSessionId(session.session_id);
        }
      } catch (err) {
        if (!abortController.signal.aborted) {
          setError(err instanceof Error ? err.message : t("sessionLoadError"));
        }
      }
    }

    loadSession();

    return () => {
      abortController.abort();
    };
  }, [initialSessionId, token, t]);

  // Cleanup: abort any in-flight SSE request on unmount
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
      abortControllerRef.current = null;
    };
  }, []);

  const sendMessage = useCallback(
    async (content: string) => {
      if (content.length > MAX_QUESTION_LENGTH) {
        setError(t("tooLong", { limit: MAX_QUESTION_LENGTH }));
        return;
      }

      if (content.trim().length === 0) {
        setError(t("empty"));
        return;
      }

      const userMessage: ChatMessage = {
        role: "user",
        content,
        sources: [],
        timestamp: new Date().toISOString(),
      };

      setMessages((prev) => [...prev, userMessage]);
      setIsLoading(true);
      setError(null);

      abortControllerRef.current?.abort();

      let lastError: unknown = null;

      for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
        const abortController = new AbortController();
        abortControllerRef.current = abortController;

        // SSE timeout
        const timeoutId = setTimeout(() => abortController.abort(), SSE_TIMEOUT_MS);

        let sseErrorMessage: string | null = null;

        try {
          const response = await chatApi.askQuestion(
            { question: content, session_id: sessionIdRef.current || undefined },
            token
          );

          if (abortController.signal.aborted) {
            clearTimeout(timeoutId);
            return;
          }

          const assistantMessage: ChatMessage = {
            role: "assistant",
            content: "",
            sources: [],
            timestamp: new Date().toISOString(),
          };

          setMessages((prev) => [...prev, assistantMessage]);

          if (response.body) {
            let fullContent = "";
            let sources: ChatSource[] = [];

            // Batched state updates to reduce re-renders during streaming
            let pendingContent = "";
            let batchTimeout: ReturnType<typeof setTimeout> | null = null;

            const flushContent = () => {
              if (pendingContent) {
                const snapshot = fullContent;
                setMessages((prev) => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  updated[updated.length - 1] = { ...last, content: snapshot };
                  return updated;
                });
                pendingContent = "";
              }
              batchTimeout = null;
            };

            await parseSSEStream(
              response.body,
              (tokenText) => {
                fullContent += tokenText;
                pendingContent += tokenText;
                if (!batchTimeout) {
                  batchTimeout = setTimeout(flushContent, TOKEN_BATCH_MS);
                }
              },
              (newSources) => {
                sources = newSources;
                setMessages((prev) => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  updated[updated.length - 1] = { ...last, sources };
                  return updated;
                });
              },
              (newSessionId) => {
                setSessionId(newSessionId);
                window.dispatchEvent(
                  new CustomEvent("chat-session-created", {
                    detail: { sessionId: newSessionId },
                  })
                );
              },
              (errMsg) => {
                sseErrorMessage = errMsg;
              },
              t("serverError")
            );

            // Flush any remaining content
            if (batchTimeout) {
              clearTimeout(batchTimeout);
            }
            if (pendingContent) {
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                updated[updated.length - 1] = { ...last, content: fullContent };
                return updated;
              });
            }

            if (sseErrorMessage) {
              setError(sseErrorMessage);
              setMessages((prev) => {
                const last = prev[prev.length - 1];
                if (last?.role === "assistant" && last.content === "") {
                  return prev.slice(0, -1);
                }
                return prev;
              });
              break;
            }
          }

          clearTimeout(timeoutId);
          abortControllerRef.current = null;
          lastError = null;
          break;
        } catch (err) {
          clearTimeout(timeoutId);
          lastError = err;

          if (err instanceof DOMException && err.name === "AbortError") {
            lastError = null;
            break;
          }

          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last?.role === "assistant" && last.content === "") {
              return prev.slice(0, -1);
            }
            return prev;
          });

          if (isNetworkError(err) && attempt < MAX_RETRIES) {
            await new Promise((r) => setTimeout(r, 1000));
            continue;
          }

          break;
        }
      }

      if (lastError) {
        const message =
          isNetworkError(lastError)
            ? t("networkError")
            : lastError instanceof Error
              ? lastError.message
              : t("unknownError");
        setError(message);
      }

      abortControllerRef.current = null;
      setIsLoading(false);
    },
    [token, t]
  );

  const clearMessages = useCallback(() => {
    setMessages([]);
    setSessionId(null);
    setError(null);
  }, []);

  return {
    messages,
    isLoading,
    error,
    sessionId,
    sendMessage,
    clearMessages,
  };
}
