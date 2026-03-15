import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock next-auth to prevent initialization issues in test env
vi.mock("next-auth", () => ({
  default: (config: any) => ({
    handlers: { GET: vi.fn(), POST: vi.fn() },
    signIn: vi.fn(),
    signOut: vi.fn(),
    auth: vi.fn(),
  }),
}));

// Mock the api module
vi.mock("@/lib/api", () => ({
  authApi: {
    login: vi.fn(),
    getMe: vi.fn(),
    refresh: vi.fn(),
  },
}));

import { authOptions } from "@/lib/auth";
import { authApi } from "@/lib/api";

const mockLogin = vi.mocked(authApi.login);
const mockGetMe = vi.mocked(authApi.getMe);

beforeEach(() => {
  vi.clearAllMocks();
});

describe("authOptions", () => {
  it("exports authOptions with credentials provider", () => {
    expect(authOptions).toBeDefined();
    expect(authOptions.providers).toBeDefined();
    expect(authOptions.providers.length).toBeGreaterThan(0);
  });

  it("uses jwt session strategy", () => {
    expect(authOptions.session?.strategy).toBe("jwt");
  });

  it("configures custom sign-in page", () => {
    expect(authOptions.pages?.signIn).toBe("/login");
  });
});

describe("credentials authorize", () => {
  function getAuthorize() {
    const credentialsProvider = authOptions.providers[0] as any;
    return credentialsProvider.options?.authorize || credentialsProvider.authorize;
  }

  it("returns user data on successful login", async () => {
    mockLogin.mockResolvedValueOnce({
      access_token: "access-123",
      refresh_token: "refresh-456",
      token_type: "bearer",
    });
    mockGetMe.mockResolvedValueOnce({
      id: "user-1",
      email: "test@example.com",
      full_name: "Test User",
      role: "student",
      faculty: "CS",
      group: "КІ-41",
      year: 4,
      department: null,
      position: null,
      is_approved: true,
      is_active: true,
      created_at: "2024-01-01T00:00:00",
      updated_at: null,
    });

    const authorize = getAuthorize();
    const result = await authorize({
      email: "test@example.com",
      password: "password123",
    });

    expect(result).not.toBeNull();
    expect(result.id).toBe("user-1");
    expect(result.email).toBe("test@example.com");
    expect(result.role).toBe("student");
    expect(result.accessToken).toBe("access-123");
    expect(result.refreshToken).toBe("refresh-456");
  });

  it("returns null on failed login", async () => {
    mockLogin.mockRejectedValueOnce(new Error("Invalid credentials"));

    const authorize = getAuthorize();
    const result = await authorize({
      email: "wrong@example.com",
      password: "wrong",
    });

    expect(result).toBeNull();
  });

  it("returns null when email or password missing", async () => {
    const authorize = getAuthorize();

    const result1 = await authorize({ email: "", password: "pass" });
    expect(result1).toBeNull();

    const result2 = await authorize({ email: "test@test.com", password: "" });
    expect(result2).toBeNull();
  });
});

describe("jwt callback", () => {
  it("stores user data in token on initial sign-in", async () => {
    const jwtCallback = authOptions.callbacks?.jwt;
    expect(jwtCallback).toBeDefined();

    const result = await jwtCallback!({
      token: { sub: "user-1" },
      user: {
        id: "user-1",
        email: "test@example.com",
        name: "Test User",
        role: "student",
        faculty: "CS",
        accessToken: "access-123",
        refreshToken: "refresh-456",
      } as any,
      trigger: "signIn",
      account: null,
      session: undefined,
    } as any);

    expect(result.role).toBe("student");
    expect(result.faculty).toBe("CS");
    expect(result.accessToken).toBe("access-123");
    expect(result.refreshToken).toBe("refresh-456");
  });

  it("passes through existing token when no user (subsequent requests)", async () => {
    const jwtCallback = authOptions.callbacks?.jwt;

    const existingToken = {
      sub: "user-1",
      role: "teacher",
      faculty: "Math",
      accessToken: "existing-access",
      refreshToken: "existing-refresh",
    };

    const result = await jwtCallback!({
      token: existingToken,
      user: undefined as any,
      trigger: "update",
      account: null,
      session: undefined,
    } as any);

    expect(result.role).toBe("teacher");
    expect(result.accessToken).toBe("existing-access");
  });
});

describe("session callback", () => {
  it("exposes user data from token to session", async () => {
    const sessionCallback = authOptions.callbacks?.session;
    expect(sessionCallback).toBeDefined();

    const result = await sessionCallback!({
      session: {
        user: { name: "", email: "", image: "" },
        expires: "2025-01-01",
      },
      token: {
        sub: "user-1",
        email: "test@example.com",
        name: "Test User",
        role: "admin",
        faculty: "IT",
        accessToken: "token-abc",
      },
    } as any);

    expect(result.user.id).toBe("user-1");
    expect(result.user.role).toBe("admin");
    expect(result.user.faculty).toBe("IT");
    expect(result.accessToken).toBe("token-abc");
  });
});
