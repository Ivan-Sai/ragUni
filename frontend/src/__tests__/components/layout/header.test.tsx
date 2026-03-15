import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Header } from "@/components/layout/header";

// Mock next-auth/react
vi.mock("next-auth/react", () => ({
  useSession: vi.fn(),
  signOut: vi.fn(),
}));

import { useSession, signOut } from "next-auth/react";

const mockUseSession = vi.mocked(useSession);
const mockSignOut = vi.mocked(signOut);

describe("Header", () => {
  it("renders the app title", () => {
    mockUseSession.mockReturnValue({
      data: null,
      status: "unauthenticated",
      update: vi.fn(),
    });

    render(<Header />);
    expect(screen.getByText("UniRAG")).toBeInTheDocument();
  });

  it("shows user name and role when authenticated", () => {
    mockUseSession.mockReturnValue({
      data: {
        user: {
          id: "1",
          name: "Іван Сай",
          email: "ivan@example.com",
          role: "student",
          faculty: "КІ",
        },
        accessToken: "token",
        expires: "2025-12-31",
      },
      status: "authenticated",
      update: vi.fn(),
    });

    render(<Header />);
    expect(screen.getByText("Іван Сай")).toBeInTheDocument();
    expect(screen.getByText("student")).toBeInTheDocument();
  });

  it("shows login link when unauthenticated", () => {
    mockUseSession.mockReturnValue({
      data: null,
      status: "unauthenticated",
      update: vi.fn(),
    });

    render(<Header />);
    const loginLink = screen.getByRole("link", { name: /увійти/i });
    expect(loginLink).toBeInTheDocument();
    expect(loginLink).toHaveAttribute("href", "/login");
  });

  it("calls signOut when logout button clicked", async () => {
    const user = userEvent.setup();
    mockUseSession.mockReturnValue({
      data: {
        user: {
          id: "1",
          name: "Test",
          email: "test@test.com",
          role: "admin",
          faculty: null,
        },
        accessToken: "token",
        expires: "2025-12-31",
      },
      status: "authenticated",
      update: vi.fn(),
    });

    render(<Header />);
    const logoutButton = screen.getByRole("button", { name: /вийти/i });
    await user.click(logoutButton);

    expect(mockSignOut).toHaveBeenCalledWith({ callbackUrl: "/login" });
  });
});
