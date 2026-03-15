import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useAdminUsers } from "@/hooks/use-admin-users";
import { adminApi } from "@/lib/api";
import type { UserResponse } from "@/types/api";

vi.mock("@/lib/api", () => ({
  adminApi: {
    getUsers: vi.fn(),
    getPendingTeachers: vi.fn(),
    approveTeacher: vi.fn(),
    rejectTeacher: vi.fn(),
    blockUser: vi.fn(),
    changeRole: vi.fn(),
  },
}));

const mockGetUsers = vi.mocked(adminApi.getUsers);
const mockGetPending = vi.mocked(adminApi.getPendingTeachers);
const mockApprove = vi.mocked(adminApi.approveTeacher);
const mockReject = vi.mocked(adminApi.rejectTeacher);
const mockBlock = vi.mocked(adminApi.blockUser);
const mockChangeRole = vi.mocked(adminApi.changeRole);

const mockUsers: UserResponse[] = [
  {
    id: "1",
    email: "admin@test.com",
    full_name: "Admin",
    role: "admin",
    faculty: null,
    group: null,
    year: null,
    department: null,
    position: null,
    is_approved: true,
    is_active: true,
    created_at: "2026-01-01",
    updated_at: null,
  },
  {
    id: "2",
    email: "student@test.com",
    full_name: "Student",
    role: "student",
    faculty: "CS",
    group: "КІ-41",
    year: 4,
    department: null,
    position: null,
    is_approved: true,
    is_active: true,
    created_at: "2026-01-02",
    updated_at: null,
  },
];

const mockPending: UserResponse[] = [
  {
    id: "3",
    email: "teacher@test.com",
    full_name: "Teacher",
    role: "teacher",
    faculty: "CS",
    group: null,
    year: null,
    department: "SE",
    position: "Доцент",
    is_approved: false,
    is_active: true,
    created_at: "2026-01-03",
    updated_at: null,
  },
];

describe("useAdminUsers", () => {
  const token = "admin-token";

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("fetches users and pending teachers on mount", async () => {
    mockGetUsers.mockResolvedValueOnce({ users: mockUsers, total: 2 });
    mockGetPending.mockResolvedValueOnce(mockPending);

    const { result } = renderHook(() => useAdminUsers({ token }));

    expect(result.current.isLoading).toBe(true);

    await vi.waitFor(() => {
      expect(result.current.users).toEqual(mockUsers);
    });

    expect(result.current.total).toBe(2);
    expect(result.current.pendingTeachers).toEqual(mockPending);
    expect(result.current.isLoading).toBe(false);
  });

  it("handles fetch error", async () => {
    mockGetUsers.mockRejectedValueOnce(new Error("Forbidden"));
    mockGetPending.mockRejectedValueOnce(new Error("Forbidden"));

    const { result } = renderHook(() => useAdminUsers({ token }));

    await vi.waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.error).toBe("Forbidden");
  });

  it("approves a teacher", async () => {
    mockGetUsers.mockResolvedValueOnce({
      users: [...mockUsers, { ...mockPending[0] }],
      total: 3,
    });
    mockGetPending.mockResolvedValueOnce(mockPending);
    mockApprove.mockResolvedValueOnce({ message: "Approved", user_id: "3" });

    const { result } = renderHook(() => useAdminUsers({ token }));

    await vi.waitFor(() => {
      expect(result.current.pendingTeachers).toHaveLength(1);
    });

    await act(async () => {
      await result.current.approveTeacher("3");
    });

    expect(mockApprove).toHaveBeenCalledWith("3", token);
    expect(result.current.pendingTeachers).toHaveLength(0);
  });

  it("rejects a teacher", async () => {
    mockGetUsers.mockResolvedValueOnce({
      users: [...mockUsers, { ...mockPending[0] }],
      total: 3,
    });
    mockGetPending.mockResolvedValueOnce(mockPending);
    mockReject.mockResolvedValueOnce({ message: "Rejected", user_id: "3" });

    const { result } = renderHook(() => useAdminUsers({ token }));

    await vi.waitFor(() => {
      expect(result.current.pendingTeachers).toHaveLength(1);
    });

    await act(async () => {
      await result.current.rejectTeacher("3");
    });

    expect(mockReject).toHaveBeenCalledWith("3", token);
    expect(result.current.pendingTeachers).toHaveLength(0);
    expect(result.current.total).toBe(2);
  });

  it("blocks a user", async () => {
    mockGetUsers.mockResolvedValueOnce({ users: mockUsers, total: 2 });
    mockGetPending.mockResolvedValueOnce([]);
    mockBlock.mockResolvedValueOnce({ message: "Blocked", user_id: "2" });

    const { result } = renderHook(() => useAdminUsers({ token }));

    await vi.waitFor(() => {
      expect(result.current.users).toHaveLength(2);
    });

    await act(async () => {
      await result.current.blockUser("2", false);
    });

    expect(mockBlock).toHaveBeenCalledWith("2", false, token);
    expect(result.current.users.find((u) => u.id === "2")?.is_active).toBe(
      false
    );
  });

  it("changes user role", async () => {
    mockGetUsers.mockResolvedValueOnce({ users: mockUsers, total: 2 });
    mockGetPending.mockResolvedValueOnce([]);
    mockChangeRole.mockResolvedValueOnce({
      message: "Changed",
      user_id: "2",
    });

    const { result } = renderHook(() => useAdminUsers({ token }));

    await vi.waitFor(() => {
      expect(result.current.users).toHaveLength(2);
    });

    await act(async () => {
      await result.current.changeRole("2", "teacher");
    });

    expect(mockChangeRole).toHaveBeenCalledWith("2", "teacher", token);
    expect(result.current.users.find((u) => u.id === "2")?.role).toBe(
      "teacher"
    );
  });

  it("does not fetch when token is empty", async () => {
    renderHook(() => useAdminUsers({ token: "" }));

    expect(mockGetUsers).not.toHaveBeenCalled();
    expect(mockGetPending).not.toHaveBeenCalled();
  });
});
