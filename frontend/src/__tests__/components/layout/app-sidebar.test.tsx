import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { AppSidebar } from "@/components/layout/app-sidebar";

// Mock next-auth/react
vi.mock("next-auth/react", () => ({
  useSession: vi.fn(),
}));

// Mock next/link
vi.mock("next/link", () => ({
  default: ({
    children,
    href,
  }: {
    children: React.ReactNode;
    href: string;
  }) => <a href={href}>{children}</a>,
}));

// Mock next/navigation
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    refresh: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    prefetch: vi.fn(),
  }),
  usePathname: () => "/chat",
}));

// Mock the sidebar primitives from shadcn
vi.mock("@/components/ui/sidebar", () => ({
  Sidebar: ({ children }: { children: React.ReactNode }) => (
    <nav data-testid="sidebar">{children}</nav>
  ),
  SidebarContent: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  SidebarGroup: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  SidebarGroupLabel: ({ children }: { children: React.ReactNode }) => (
    <span>{children}</span>
  ),
  SidebarGroupContent: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  SidebarMenu: ({ children }: { children: React.ReactNode }) => (
    <ul>{children}</ul>
  ),
  SidebarMenuItem: ({ children }: { children: React.ReactNode }) => (
    <li>{children}</li>
  ),
  SidebarMenuButton: ({
    children,
    render: renderProp,
  }: {
    children: React.ReactNode;
    render?: React.ReactElement;
  }) => (renderProp ? <>{renderProp}{children}</> : <button>{children}</button>),
  SidebarHeader: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  SidebarFooter: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));

import { useSession } from "next-auth/react";
const mockUseSession = vi.mocked(useSession);

describe("AppSidebar", () => {
  it("renders chat navigation link for all authenticated users", () => {
    mockUseSession.mockReturnValue({
      data: {
        user: { id: "1", name: "Test", email: "t@t.com", role: "student", faculty: "CS" },
        accessToken: "token",
        expires: "2025-12-31",
      },
      status: "authenticated",
      update: vi.fn(),
    });

    render(<AppSidebar />);
    expect(screen.getByText("Чат")).toBeInTheDocument();
  });

  it("shows admin links only for admin users", () => {
    mockUseSession.mockReturnValue({
      data: {
        user: { id: "1", name: "Admin", email: "a@a.com", role: "admin", faculty: null },
        accessToken: "token",
        expires: "2025-12-31",
      },
      status: "authenticated",
      update: vi.fn(),
    });

    render(<AppSidebar />);
    expect(screen.getByText("Документи")).toBeInTheDocument();
    expect(screen.getByText("Користувачі")).toBeInTheDocument();
  });

  it("hides admin links for student users", () => {
    mockUseSession.mockReturnValue({
      data: {
        user: { id: "1", name: "Student", email: "s@s.com", role: "student", faculty: "CS" },
        accessToken: "token",
        expires: "2025-12-31",
      },
      status: "authenticated",
      update: vi.fn(),
    });

    render(<AppSidebar />);
    expect(screen.getByText("Чат")).toBeInTheDocument();
    expect(screen.queryByText("Користувачі")).not.toBeInTheDocument();
  });

  it("hides admin links for teacher users", () => {
    mockUseSession.mockReturnValue({
      data: {
        user: { id: "1", name: "Teacher", email: "t@t.com", role: "teacher", faculty: "Math" },
        accessToken: "token",
        expires: "2025-12-31",
      },
      status: "authenticated",
      update: vi.fn(),
    });

    render(<AppSidebar />);
    expect(screen.getByText("Чат")).toBeInTheDocument();
    expect(screen.queryByText("Користувачі")).not.toBeInTheDocument();
  });
});
