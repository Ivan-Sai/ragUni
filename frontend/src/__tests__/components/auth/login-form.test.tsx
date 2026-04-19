import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LoginForm } from "@/components/auth/login-form";

// Mock next-auth/react
vi.mock("next-auth/react", () => ({
  signIn: vi.fn(),
}));

// Mock next/navigation
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    refresh: vi.fn(),
  }),
}));

import { signIn } from "next-auth/react";
const mockSignIn = vi.mocked(signIn);

beforeEach(() => {
  vi.clearAllMocks();
});

describe("LoginForm", () => {
  it("renders email and password fields", () => {
    render(<LoginForm />);

    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/пароль/i)).toBeInTheDocument();
  });

  it("renders a submit button", () => {
    render(<LoginForm />);

    expect(
      screen.getByRole("button", { name: /увійти/i })
    ).toBeInTheDocument();
  });

  it("renders a link to register page", () => {
    render(<LoginForm />);

    const registerLink = screen.getByRole("link", {
      name: /зареєструватися/i,
    });
    expect(registerLink).toBeInTheDocument();
    expect(registerLink).toHaveAttribute("href", "/register");
  });

  it("calls signIn with credentials on submit", async () => {
    const user = userEvent.setup();
    mockSignIn.mockResolvedValueOnce({ ok: true, error: undefined });

    render(<LoginForm />);

    await user.type(screen.getByLabelText(/email/i), "test@example.com");
    await user.type(screen.getByLabelText(/пароль/i), "password123");
    await user.click(screen.getByRole("button", { name: /увійти/i }));

    await waitFor(() => {
      expect(mockSignIn).toHaveBeenCalledWith("credentials", {
        email: "test@example.com",
        password: "password123",
        redirect: false,
      });
    });
  });

  it("shows validation error for short password", async () => {
    const user = userEvent.setup();

    render(<LoginForm />);

    await user.type(screen.getByLabelText(/email/i), "test@example.com");
    await user.type(screen.getByLabelText(/пароль/i), "short");
    await user.click(screen.getByRole("button", { name: /увійти/i }));

    await waitFor(() => {
      expect(screen.getByText(/8/)).toBeInTheDocument();
    });

    // signIn should NOT be called when validation fails
    expect(mockSignIn).not.toHaveBeenCalled();
  });

  it("shows error message on failed login", async () => {
    const user = userEvent.setup();
    mockSignIn.mockResolvedValueOnce({
      ok: false,
      error: "CredentialsSignin",
    });

    render(<LoginForm />);

    await user.type(screen.getByLabelText(/email/i), "wrong@example.com");
    await user.type(screen.getByLabelText(/пароль/i), "wrongpassword");
    await user.click(screen.getByRole("button", { name: /увійти/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/невірна електронна пошта або пароль/i)
      ).toBeInTheDocument();
    });
  });

  it("disables submit button while loading", async () => {
    const user = userEvent.setup();
    // Make signIn hang indefinitely
    mockSignIn.mockReturnValue(new Promise(() => {}));

    render(<LoginForm />);

    await user.type(screen.getByLabelText(/email/i), "test@example.com");
    await user.type(screen.getByLabelText(/пароль/i), "password123");
    await user.click(screen.getByRole("button", { name: /увійти/i }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /увійти/i })).toBeDisabled();
    });
  });
});
