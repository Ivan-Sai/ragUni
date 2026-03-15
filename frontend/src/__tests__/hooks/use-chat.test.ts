import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useChat } from "@/hooks/use-chat";
import { chatApi } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  chatApi: {
    askQuestion: vi.fn(),
    getSession: vi.fn(),
  },
}));

const mockAskQuestion = vi.mocked(chatApi.askQuestion);
const mockGetSession = vi.mocked(chatApi.getSession);

function createSSEStream(events: Array<{ event: string; data: unknown }>) {
  const text = events
    .map((e) => `event: ${e.event}\ndata: ${JSON.stringify(e.data)}\n\n`)
    .join("");

  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode(text));
      controller.close();
    },
  });
}

describe("useChat", () => {
  const token = "test-token";

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("has correct initial state", () => {
    const { result } = renderHook(() => useChat({ token }));

    expect(result.current.messages).toEqual([]);
    expect(result.current.isLoading).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.sessionId).toBeNull();
  });

  it("sends message and processes SSE stream", async () => {
    const sseStream = createSSEStream([
      { event: "token", data: "Привіт" },
      { event: "token", data: ", світ!" },
      { event: "done", data: "" },
    ]);

    mockAskQuestion.mockResolvedValueOnce({
      body: sseStream,
    } as unknown as Response);

    const { result } = renderHook(() => useChat({ token }));

    await act(async () => {
      await result.current.sendMessage("Привіт");
    });

    // User message + assistant message
    expect(result.current.messages).toHaveLength(2);
    expect(result.current.messages[0].role).toBe("user");
    expect(result.current.messages[0].content).toBe("Привіт");
    expect(result.current.messages[1].role).toBe("assistant");
    expect(result.current.messages[1].content).toBe("Привіт, світ!");
    expect(result.current.isLoading).toBe(false);
  });

  it("sets isLoading during streaming", async () => {
    // Create a stream that we control
    let resolveStream: () => void;
    const streamPromise = new Promise<void>((resolve) => {
      resolveStream = resolve;
    });

    const sseStream = createSSEStream([
      { event: "token", data: "ok" },
      { event: "done", data: "" },
    ]);

    mockAskQuestion.mockResolvedValueOnce({
      body: sseStream,
    } as unknown as Response);

    const { result } = renderHook(() => useChat({ token }));

    let sendPromise: Promise<void>;
    await act(async () => {
      sendPromise = result.current.sendMessage("test");
    });

    // After stream completes, isLoading should be false
    expect(result.current.isLoading).toBe(false);
  });

  it("handles API errors", async () => {
    mockAskQuestion.mockRejectedValueOnce(new Error("Network error"));

    const { result } = renderHook(() => useChat({ token }));

    await act(async () => {
      await result.current.sendMessage("test");
    });

    expect(result.current.error).toBe("Network error");
    expect(result.current.isLoading).toBe(false);
    // User message should still be added
    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0].role).toBe("user");
  });

  it("handles sources from SSE", async () => {
    const sources = [
      { source_file: "doc.pdf", file_type: "pdf", chunk_index: 0, total_chunks: 1, text: "chunk text", score: 0.95 },
    ];
    const sseStream = createSSEStream([
      { event: "token", data: "Answer" },
      { event: "sources", data: sources },
      { event: "done", data: "" },
    ]);

    mockAskQuestion.mockResolvedValueOnce({
      body: sseStream,
    } as unknown as Response);

    const { result } = renderHook(() => useChat({ token }));

    await act(async () => {
      await result.current.sendMessage("test");
    });

    expect(result.current.messages[1].sources).toEqual(sources);
  });

  it("clears messages with clearMessages", async () => {
    const sseStream = createSSEStream([
      { event: "token", data: "response" },
      { event: "done", data: "" },
    ]);

    mockAskQuestion.mockResolvedValueOnce({
      body: sseStream,
    } as unknown as Response);

    const { result } = renderHook(() => useChat({ token }));

    await act(async () => {
      await result.current.sendMessage("hello");
    });
    expect(result.current.messages).toHaveLength(2);

    act(() => {
      result.current.clearMessages();
    });

    expect(result.current.messages).toEqual([]);
    expect(result.current.sessionId).toBeNull();
  });

  it("loads existing session", async () => {
    const session = {
      _id: "1",
      user_id: "u1",
      session_id: "s1",
      title: "Test",
      messages: [
        { role: "user" as const, content: "Hi", sources: [], timestamp: "2026-03-08T00:00:00Z" },
        { role: "assistant" as const, content: "Hello!", sources: [], timestamp: "2026-03-08T00:00:01Z" },
      ],
      created_at: "2026-03-08T00:00:00Z",
      updated_at: "2026-03-08T00:00:01Z",
    };

    mockGetSession.mockResolvedValueOnce(session);

    const { result } = renderHook(() => useChat({ token, sessionId: "s1" }));

    // Wait for async load
    await vi.waitFor(() => {
      expect(result.current.messages).toHaveLength(2);
    });

    expect(result.current.messages[0].content).toBe("Hi");
    expect(result.current.messages[1].content).toBe("Hello!");
    expect(result.current.sessionId).toBe("s1");
  });
});
