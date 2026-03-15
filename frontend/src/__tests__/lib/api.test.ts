import { describe, it, expect, vi, beforeEach } from "vitest";
import { apiClient, authApi } from "@/lib/api";

// Mock fetch globally
const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

beforeEach(() => {
  mockFetch.mockReset();
});

describe("apiClient", () => {
  it("makes GET requests to the correct URL", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ data: "test" }),
    });

    const result = await apiClient.get("/test");

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/test"),
      expect.objectContaining({ method: "GET" })
    );
    expect(result).toEqual({ data: "test" });
  });

  it("makes POST requests with JSON body", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: "1" }),
    });

    const result = await apiClient.post("/test", { name: "value" });

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/test"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ name: "value" }),
      })
    );
    expect(result).toEqual({ id: "1" });
  });

  it("includes Authorization header when token provided", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({}),
    });

    await apiClient.get("/me", { token: "test-token" });

    expect(mockFetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer test-token",
        }),
      })
    );
  });

  it("throws ApiError on non-ok response", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 401,
      json: async () => ({ detail: "Unauthorized" }),
    });

    await expect(apiClient.get("/protected")).rejects.toThrow("Unauthorized");
  });

  it("throws generic error when response has no detail", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => ({}),
    });

    await expect(apiClient.get("/broken")).rejects.toThrow("Помилка сервера");
  });
});

describe("authApi", () => {
  it("login sends form-urlencoded data", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        access_token: "abc",
        refresh_token: "def",
        token_type: "bearer",
      }),
    });

    const result = await authApi.login({
      email: "test@example.com",
      password: "password123",
    });

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/auth/login"),
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "Content-Type": "application/x-www-form-urlencoded",
        }),
      })
    );
    expect(result.access_token).toBe("abc");
  });

  it("register sends JSON data", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        id: "1",
        email: "test@example.com",
        full_name: "Test User",
        role: "student",
      }),
    });

    const result = await authApi.register({
      email: "test@example.com",
      password: "password123",
      full_name: "Test User",
      role: "student",
      faculty: "CS",
    });

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/auth/register"),
      expect.objectContaining({
        method: "POST",
        body: expect.any(String),
      })
    );
    expect(result.email).toBe("test@example.com");
  });

  it("refresh sends refresh_token in JSON body", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        access_token: "new-token",
        token_type: "bearer",
      }),
    });

    const result = await authApi.refresh("old-refresh-token");

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/auth/refresh"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ refresh_token: "old-refresh-token" }),
      })
    );
    expect(result.access_token).toBe("new-token");
  });

  it("getMe sends token in Authorization header", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        id: "1",
        email: "test@example.com",
        role: "student",
      }),
    });

    const result = await authApi.getMe("my-token");

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/auth/me"),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer my-token",
        }),
      })
    );
    expect(result.id).toBe("1");
  });
});
