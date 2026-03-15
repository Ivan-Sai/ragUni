import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PendingTeachers } from "@/components/admin/pending-teachers";
import type { UserResponse } from "@/types/api";

const mockTeachers: UserResponse[] = [
  {
    id: "1",
    email: "teacher@test.com",
    full_name: "Іван Петрович",
    role: "teacher",
    faculty: "КІ",
    group: null,
    year: null,
    department: "ПІ",
    position: "Доцент",
    is_approved: false,
    is_active: true,
    created_at: "2026-03-01",
    updated_at: null,
  },
];

describe("PendingTeachers", () => {
  it("renders nothing when no pending teachers and not loading", () => {
    const { container } = render(
      <PendingTeachers
        teachers={[]}
        onApprove={vi.fn()}
        onReject={vi.fn()}
        isLoading={false}
      />
    );

    expect(container.innerHTML).toBe("");
  });

  it("renders teacher info", () => {
    render(
      <PendingTeachers
        teachers={mockTeachers}
        onApprove={vi.fn()}
        onReject={vi.fn()}
        isLoading={false}
      />
    );

    expect(screen.getByText("Іван Петрович")).toBeInTheDocument();
    expect(screen.getByText("teacher@test.com")).toBeInTheDocument();
    expect(screen.getByText("КІ")).toBeInTheDocument();
  });

  it("calls onApprove when approve button clicked", async () => {
    const user = userEvent.setup();
    const onApprove = vi.fn();

    render(
      <PendingTeachers
        teachers={mockTeachers}
        onApprove={onApprove}
        onReject={vi.fn()}
        isLoading={false}
      />
    );

    const buttons = screen.getAllByRole("button");
    // First button is approve (Check icon)
    await user.click(buttons[0]);

    expect(onApprove).toHaveBeenCalledWith("1");
  });

  it("calls onReject when reject button clicked", async () => {
    const user = userEvent.setup();
    const onReject = vi.fn();

    render(
      <PendingTeachers
        teachers={mockTeachers}
        onApprove={vi.fn()}
        onReject={onReject}
        isLoading={false}
      />
    );

    const buttons = screen.getAllByRole("button");
    // Second button is reject (X icon)
    await user.click(buttons[1]);

    expect(onReject).toHaveBeenCalledWith("1");
  });

  it("shows badge with count", () => {
    render(
      <PendingTeachers
        teachers={mockTeachers}
        onApprove={vi.fn()}
        onReject={vi.fn()}
        isLoading={false}
      />
    );

    expect(screen.getByText("1")).toBeInTheDocument();
  });
});
