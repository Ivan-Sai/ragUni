import { describe, it, expect, vi, beforeEach } from "vitest";
import { adminApi, documentsApi } from "@/lib/api";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

beforeEach(() => {
  mockFetch.mockReset();
});

describe("adminApi", () => {
  it("getUsers fetches users with pagination", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ users: [{ id: "1" }], total: 1 }),
    });

    const result = await adminApi.getUsers("token", 0, 10);

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/admin/users?skip=0&limit=10"),
      expect.objectContaining({
        method: "GET",
        headers: expect.objectContaining({
          Authorization: "Bearer token",
        }),
      })
    );
    expect(result.users).toHaveLength(1);
    expect(result.total).toBe(1);
  });

  it("getPendingTeachers fetches pending list", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [{ id: "2", role: "teacher", is_approved: false }],
    });

    const result = await adminApi.getPendingTeachers("token");

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/admin/users/pending"),
      expect.objectContaining({ method: "GET" })
    );
    expect(result).toHaveLength(1);
    expect(result[0].is_approved).toBe(false);
  });

  it("approveTeacher sends PUT request", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ message: "Approved", user_id: "2" }),
    });

    const result = await adminApi.approveTeacher("2", "token");

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/admin/users/2/approve"),
      expect.objectContaining({ method: "PUT" })
    );
    expect(result.message).toBe("Approved");
  });

  it("rejectTeacher sends PUT request", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ message: "Rejected", user_id: "2" }),
    });

    const result = await adminApi.rejectTeacher("2", "token");

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/admin/users/2/reject"),
      expect.objectContaining({ method: "PUT" })
    );
    expect(result.message).toBe("Rejected");
  });

  it("blockUser sends is_active in body", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ message: "Blocked", user_id: "3" }),
    });

    const result = await adminApi.blockUser("3", false, "token");

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/admin/users/3/block"),
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ is_active: false }),
      })
    );
    expect(result.message).toBe("Blocked");
  });

  it("changeRole sends new role in body", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ message: "Role changed", user_id: "3" }),
    });

    const result = await adminApi.changeRole("3", "admin", "token");

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/admin/users/3/role"),
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ role: "admin" }),
      })
    );
    expect(result.message).toBe("Role changed");
  });
});

describe("documentsApi", () => {
  it("list fetches documents", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        documents: [{ id: "1", filename: "test.pdf" }],
        total: 1,
      }),
    });

    const result = await documentsApi.list("token");

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/documents/list"),
      expect.objectContaining({ method: "GET" })
    );
    expect(result.documents).toHaveLength(1);
  });

  it("delete sends DELETE request", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        message: "Deleted",
        filename: "test.pdf",
        chunks_deleted: 5,
      }),
    });

    const result = await documentsApi.delete("doc1", "token");

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/documents/doc1"),
      expect.objectContaining({ method: "DELETE" })
    );
    expect(result.chunks_deleted).toBe(5);
  });

  it("upload sends FormData with file", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        id: "new-doc",
        filename: "test.pdf",
        file_type: "pdf",
        uploaded_at: "2026-01-01",
        total_chunks: 10,
        message: "Success",
      }),
    });

    const file = new File(["content"], "test.pdf", { type: "application/pdf" });
    const result = await documentsApi.upload(file, "token");

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/documents/upload"),
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          Authorization: "Bearer token",
        }),
      })
    );
    expect(result.id).toBe("new-doc");
    expect(result.total_chunks).toBe(10);
  });

  it("upload throws ApiError on failure", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 400,
      json: async () => ({ detail: "File too large" }),
    });

    const file = new File(["content"], "huge.pdf", { type: "application/pdf" });

    await expect(documentsApi.upload(file, "token")).rejects.toThrow(
      "File too large"
    );
  });

  it("getStats fetches document statistics", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        documents: { total: 5, by_type: { pdf: 3, docx: 2 } },
        vector_store: { total_documents: 50 },
      }),
    });

    const result = await documentsApi.getStats("token");

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/documents/stats"),
      expect.objectContaining({ method: "GET" })
    );
    expect(result.documents.total).toBe(5);
  });

  it("getHealth fetches system health", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        status: "healthy",
        components: {},
        statistics: {},
        configuration: {},
      }),
    });

    const result = await documentsApi.getHealth("token");

    expect(result.status).toBe("healthy");
  });
});
