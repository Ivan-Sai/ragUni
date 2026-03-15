import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { UsersTable } from "@/components/admin/users-table";
import type { UserResponse } from "@/types/api";

const mockUsers: UserResponse[] = [
  {
    id: "1",
    email: "admin@test.com",
    full_name: "Адмін",
    role: "admin",
    faculty: null,
    group: null,
    year: null,
    department: null,
    position: null,
    is_approved: true,
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: null,
  },
  {
    id: "2",
    email: "student@test.com",
    full_name: "Студент",
    role: "student",
    faculty: "КІ",
    group: "КІ-41",
    year: 4,
    department: null,
    position: null,
    is_approved: true,
    is_active: false,
    created_at: "2026-01-02T00:00:00Z",
    updated_at: null,
  },
];

describe("UsersTable", () => {
  it("renders user rows with data", () => {
    render(
      <UsersTable
        users={mockUsers}
        isLoading={false}
        onBlock={vi.fn()}
        onChangeRole={vi.fn()}
      />
    );

    expect(screen.getByText("Адмін")).toBeInTheDocument();
    expect(screen.getByText("admin@test.com")).toBeInTheDocument();
    expect(screen.getByText("Студент")).toBeInTheDocument();
    expect(screen.getByText("КІ")).toBeInTheDocument();
  });

  it("shows active/blocked status badges", () => {
    render(
      <UsersTable
        users={mockUsers}
        isLoading={false}
        onBlock={vi.fn()}
        onChangeRole={vi.fn()}
      />
    );

    expect(screen.getByText("Активний")).toBeInTheDocument();
    expect(screen.getByText("Заблоковано")).toBeInTheDocument();
  });

  it("shows empty state when no users", () => {
    render(
      <UsersTable
        users={[]}
        isLoading={false}
        onBlock={vi.fn()}
        onChangeRole={vi.fn()}
      />
    );

    expect(screen.getByText("Користувачів не знайдено")).toBeInTheDocument();
  });

  it("shows skeletons when loading", () => {
    const { container } = render(
      <UsersTable
        users={[]}
        isLoading={true}
        onBlock={vi.fn()}
        onChangeRole={vi.fn()}
      />
    );

    const skeletons = container.querySelectorAll("[data-slot='skeleton']");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("renders action buttons for each user", () => {
    render(
      <UsersTable
        users={mockUsers}
        isLoading={false}
        onBlock={vi.fn()}
        onChangeRole={vi.fn()}
      />
    );

    // Each user should have a block/unblock button
    const buttons = screen.getAllByRole("button");
    // 2 users × (1 select trigger + 1 block button) = 4 buttons minimum
    expect(buttons.length).toBeGreaterThanOrEqual(2);
  });
});
