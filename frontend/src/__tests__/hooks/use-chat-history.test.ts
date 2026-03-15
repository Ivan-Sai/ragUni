import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useChatHistory } from "@/hooks/use-chat-history";
import { chatApi } from "@/lib/api";
import type { ChatSessionPreview } from "@/types/api";

vi.mock("@/lib/api", () => ({
  chatApi: {
    getHistory: vi.fn(),
    deleteSession: vi.fn(),
  },
}));

const mockGetHistory = vi.mocked(chatApi.getHistory);
const mockDeleteSession = vi.mocked(chatApi.deleteSession);

const mockSessions: ChatSessionPreview[] = [
  {
    _id: "1",
    user_id: "u1",
    session_id: "s1",
    title: "Перша сесія",
    created_at: "2026-03-08T00:00:00Z",
    updated_at: "2026-03-08T01:00:00Z",
  },
  {
    _id: "2",
    user_id: "u1",
    session_id: "s2",
    title: "Друга сесія",
    created_at: "2026-03-07T00:00:00Z",
    updated_at: "2026-03-07T01:00:00Z",
  },
];

describe("useChatHistory", () => {
  const token = "test-token";

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("fetches sessions on mount", async () => {
    mockGetHistory.mockResolvedValueOnce(mockSessions);

    const { result } = renderHook(() => useChatHistory({ token }));

    expect(result.current.isLoading).toBe(true);

    await vi.waitFor(() => {
      expect(result.current.sessions).toEqual(mockSessions);
    });

    expect(result.current.isLoading).toBe(false);
    expect(mockGetHistory).toHaveBeenCalledWith(token);
  });

  it("handles fetch error", async () => {
    mockGetHistory.mockRejectedValueOnce(new Error("Network error"));

    const { result } = renderHook(() => useChatHistory({ token }));

    await vi.waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.error).toBe("Network error");
    expect(result.current.sessions).toEqual([]);
  });

  it("deletes a session", async () => {
    mockGetHistory.mockResolvedValueOnce(mockSessions);
    mockDeleteSession.mockResolvedValueOnce({ message: "Сесію видалено" });

    const { result } = renderHook(() => useChatHistory({ token }));

    await vi.waitFor(() => {
      expect(result.current.sessions).toHaveLength(2);
    });

    await act(async () => {
      await result.current.deleteSession("s1");
    });

    expect(mockDeleteSession).toHaveBeenCalledWith("s1", token);
    expect(result.current.sessions).toHaveLength(1);
    expect(result.current.sessions[0].session_id).toBe("s2");
  });

  it("refreshes sessions list", async () => {
    mockGetHistory.mockResolvedValueOnce(mockSessions);

    const { result } = renderHook(() => useChatHistory({ token }));

    await vi.waitFor(() => {
      expect(result.current.sessions).toHaveLength(2);
    });

    const updatedSessions = [...mockSessions, {
      _id: "3",
      user_id: "u1",
      session_id: "s3",
      title: "Третя сесія",
      created_at: "2026-03-09T00:00:00Z",
      updated_at: "2026-03-09T01:00:00Z",
    }];

    mockGetHistory.mockResolvedValueOnce(updatedSessions);

    await act(async () => {
      await result.current.refresh();
    });

    expect(result.current.sessions).toHaveLength(3);
  });

  it("does not fetch when token is empty", async () => {
    const { result } = renderHook(() => useChatHistory({ token: "" }));

    expect(result.current.sessions).toEqual([]);
    expect(mockGetHistory).not.toHaveBeenCalled();
  });
});
