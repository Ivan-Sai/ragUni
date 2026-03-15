import { describe, it, expect, vi, beforeEach } from "vitest";
import { chatApi } from "@/lib/api";
import type { ChatSession, ChatSessionPreview } from "@/types/api";

// Mock global fetch
const mockFetch = vi.fn();
global.fetch = mockFetch;

beforeEach(() => {
  mockFetch.mockReset();
});

describe("chatApi", () => {
  const token = "test-access-token";

  describe("getHistory", () => {
    it("fetches chat sessions list", async () => {
      const sessions: ChatSessionPreview[] = [
        {
          _id: "1",
          user_id: "u1",
          session_id: "s1",
          title: "Test session",
          created_at: "2026-03-08T00:00:00Z",
          updated_at: "2026-03-08T00:00:00Z",
        },
      ];

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => sessions,
      });

      const result = await chatApi.getHistory(token);

      expect(result).toEqual(sessions);
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/v1/chat/history"),
        expect.objectContaining({
          method: "GET",
          headers: expect.objectContaining({
            Authorization: `Bearer ${token}`,
          }),
        })
      );
    });
  });

  describe("getSession", () => {
    it("fetches a specific chat session with messages", async () => {
      const session: ChatSession = {
        _id: "1",
        user_id: "u1",
        session_id: "s1",
        title: "Test session",
        messages: [
          {
            role: "user",
            content: "Hello",
            sources: [],
            timestamp: "2026-03-08T00:00:00Z",
          },
        ],
        created_at: "2026-03-08T00:00:00Z",
        updated_at: "2026-03-08T00:00:00Z",
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => session,
      });

      const result = await chatApi.getSession("s1", token);

      expect(result).toEqual(session);
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/v1/chat/history/s1"),
        expect.objectContaining({
          method: "GET",
          headers: expect.objectContaining({
            Authorization: `Bearer ${token}`,
          }),
        })
      );
    });
  });

  describe("deleteSession", () => {
    it("deletes a chat session", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ message: "Сесію видалено" }),
      });

      const result = await chatApi.deleteSession("s1", token);

      expect(result).toEqual({ message: "Сесію видалено" });
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/v1/chat/history/s1"),
        expect.objectContaining({
          method: "DELETE",
          headers: expect.objectContaining({
            Authorization: `Bearer ${token}`,
          }),
        })
      );
    });
  });

  describe("askQuestion", () => {
    it("sends POST to /chat/ask with SSE and returns response", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: { get: () => "text/event-stream" },
        body: new ReadableStream(),
      });

      const response = await chatApi.askQuestion(
        { question: "Що таке RAG?", session_id: "s1" },
        token
      );

      expect(response).toBeDefined();
      expect(response.body).toBeInstanceOf(ReadableStream);
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/v1/chat/ask"),
        expect.objectContaining({
          method: "POST",
          headers: expect.objectContaining({
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          }),
          body: JSON.stringify({ question: "Що таке RAG?", session_id: "s1" }),
        })
      );
    });

    it("throws on non-ok response", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: async () => ({ detail: "Не авторизовано" }),
      });

      await expect(
        chatApi.askQuestion({ question: "test" }, token)
      ).rejects.toThrow("Не авторизовано");
    });
  });
});
