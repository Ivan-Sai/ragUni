import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeToggle } from "@/components/layout/theme-toggle";

// Mock next-themes
vi.mock("next-themes", () => ({
  useTheme: vi.fn(),
}));

import { useTheme } from "next-themes";
const mockUseTheme = vi.mocked(useTheme);

describe("ThemeToggle", () => {
  it("renders a toggle button", () => {
    mockUseTheme.mockReturnValue({
      theme: "light",
      setTheme: vi.fn(),
      themes: ["light", "dark"],
      resolvedTheme: "light",
      systemTheme: "light",
      forcedTheme: undefined,
    });

    render(<ThemeToggle />);
    expect(screen.getByRole("button", { name: "Змінити тему" })).toBeInTheDocument();
  });

  it("switches to dark theme when currently light", async () => {
    const setTheme = vi.fn();
    const user = userEvent.setup();
    mockUseTheme.mockReturnValue({
      theme: "light",
      setTheme,
      themes: ["light", "dark"],
      resolvedTheme: "light",
      systemTheme: "light",
      forcedTheme: undefined,
    });

    render(<ThemeToggle />);
    await user.click(screen.getByRole("button", { name: "Змінити тему" }));

    expect(setTheme).toHaveBeenCalledWith("dark");
  });

  it("switches to light theme when currently dark", async () => {
    const setTheme = vi.fn();
    const user = userEvent.setup();
    mockUseTheme.mockReturnValue({
      theme: "dark",
      setTheme,
      themes: ["light", "dark"],
      resolvedTheme: "dark",
      systemTheme: "light",
      forcedTheme: undefined,
    });

    render(<ThemeToggle />);
    await user.click(screen.getByRole("button", { name: "Змінити тему" }));

    expect(setTheme).toHaveBeenCalledWith("light");
  });
});
