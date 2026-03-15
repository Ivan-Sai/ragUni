import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RegisterForm } from "@/components/auth/register-form";

// Mock the api module
vi.mock("@/lib/api", () => ({
  authApi: {
    register: vi.fn(),
  },
}));

// Mock next/navigation
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mockPush,
    replace: vi.fn(),
    refresh: vi.fn(),
  }),
}));

import { authApi } from "@/lib/api";
const mockRegister = vi.mocked(authApi.register);
const mockPush = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
});

describe("RegisterForm", () => {
  it("renders common fields: email, password, full name, faculty", () => {
    render(<RegisterForm />);

    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/пароль/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/повне ім'я/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/факультет/i)).toBeInTheDocument();
  });

  it("renders role selector with student and teacher options", () => {
    render(<RegisterForm />);

    expect(screen.getByText("Роль")).toBeInTheDocument();
  });

  it("shows student-specific fields by default", () => {
    render(<RegisterForm />);

    expect(screen.getByLabelText(/група/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/курс/i)).toBeInTheDocument();
  });

  it("shows teacher-specific fields when teacher role selected", async () => {
    const user = userEvent.setup();
    render(<RegisterForm />);

    // Click the role selector trigger
    const roleSelect = screen.getByRole("combobox");
    await user.click(roleSelect);

    // Select teacher
    const teacherOption = await screen.findByRole("option", {
      name: /викладач/i,
    });
    await user.click(teacherOption);

    await waitFor(() => {
      expect(screen.getByLabelText(/кафедра/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/посада/i)).toBeInTheDocument();
    });
  });

  it("renders a link to login page", () => {
    render(<RegisterForm />);

    const loginLink = screen.getByRole("link", { name: /увійти/i });
    expect(loginLink).toBeInTheDocument();
    expect(loginLink).toHaveAttribute("href", "/login");
  });

  it("submits student registration data", async () => {
    const user = userEvent.setup();
    mockRegister.mockResolvedValueOnce({
      id: "1",
      email: "student@example.com",
      full_name: "Student Name",
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

    render(<RegisterForm />);

    await user.type(screen.getByLabelText(/email/i), "student@example.com");
    await user.type(screen.getByLabelText(/пароль/i), "password123");
    await user.type(screen.getByLabelText(/повне ім'я/i), "Student Name");
    await user.type(screen.getByLabelText(/факультет/i), "CS");
    await user.type(screen.getByLabelText(/група/i), "КІ-41");
    await user.type(screen.getByLabelText(/курс/i), "4");

    await user.click(screen.getByRole("button", { name: /зареєструватися/i }));

    await waitFor(() => {
      expect(mockRegister).toHaveBeenCalledWith(
        expect.objectContaining({
          email: "student@example.com",
          password: "password123",
          full_name: "Student Name",
          role: "student",
          faculty: "CS",
          group: "КІ-41",
          year: 4,
        })
      );
    });
  });

  it("redirects to login on successful registration", async () => {
    const user = userEvent.setup();
    mockRegister.mockResolvedValueOnce({
      id: "1",
      email: "test@example.com",
      full_name: "Test",
      role: "student",
      faculty: "CS",
      group: null,
      year: null,
      department: null,
      position: null,
      is_approved: true,
      is_active: true,
      created_at: "2024-01-01T00:00:00",
      updated_at: null,
    });

    render(<RegisterForm />);

    await user.type(screen.getByLabelText(/email/i), "test@example.com");
    await user.type(screen.getByLabelText(/пароль/i), "password123");
    await user.type(screen.getByLabelText(/повне ім'я/i), "Test");
    await user.type(screen.getByLabelText(/факультет/i), "CS");

    await user.click(screen.getByRole("button", { name: /зареєструватися/i }));

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith("/login");
    });
  });

  it("shows error message on failed registration", async () => {
    const user = userEvent.setup();
    mockRegister.mockRejectedValueOnce(
      new Error("Користувач з такою електронною поштою вже існує")
    );

    render(<RegisterForm />);

    await user.type(screen.getByLabelText(/email/i), "exists@example.com");
    await user.type(screen.getByLabelText(/пароль/i), "password123");
    await user.type(screen.getByLabelText(/повне ім'я/i), "Test");
    await user.type(screen.getByLabelText(/факультет/i), "CS");

    await user.click(screen.getByRole("button", { name: /зареєструватися/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/Користувач з такою електронною поштою вже існує/i)
      ).toBeInTheDocument();
    });
  });
});
