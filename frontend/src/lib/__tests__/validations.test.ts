import { describe, it, expect } from "vitest";
import { loginSchema, registerSchema } from "../validations";

describe("loginSchema", () => {
  it("accepts valid login data", () => {
    const result = loginSchema.safeParse({
      email: "user@university.edu",
      password: "SecurePass1",
    });
    expect(result.success).toBe(true);
  });

  it("rejects empty email", () => {
    const result = loginSchema.safeParse({
      email: "",
      password: "SecurePass1",
    });
    expect(result.success).toBe(false);
  });

  it("rejects invalid email format", () => {
    const result = loginSchema.safeParse({
      email: "not-an-email",
      password: "SecurePass1",
    });
    expect(result.success).toBe(false);
  });

  it("rejects short password", () => {
    const result = loginSchema.safeParse({
      email: "user@university.edu",
      password: "short",
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0]?.message).toContain("8");
    }
  });

  it("rejects empty password", () => {
    const result = loginSchema.safeParse({
      email: "user@university.edu",
      password: "",
    });
    expect(result.success).toBe(false);
  });
});

describe("registerSchema", () => {
  it("accepts valid student data", () => {
    const result = registerSchema.safeParse({
      email: "student@university.edu",
      password: "SecurePass1",
      full_name: "Іванов Іван",
      role: "student",
      faculty: "Факультет комп'ютерних наук",
      group: "КІ-41",
      year: 4,
    });
    expect(result.success).toBe(true);
  });

  it("accepts valid teacher data", () => {
    const result = registerSchema.safeParse({
      email: "teacher@university.edu",
      password: "SecurePass1",
      full_name: "Петренко Петро",
      role: "teacher",
      faculty: "Факультет комп'ютерних наук",
      department: "Кафедра ІС",
      position: "Доцент",
    });
    expect(result.success).toBe(true);
  });

  it("rejects invalid role", () => {
    const result = registerSchema.safeParse({
      email: "user@university.edu",
      password: "SecurePass1",
      full_name: "Іванов Іван",
      role: "admin",
      faculty: "ФКН",
    });
    expect(result.success).toBe(false);
  });

  it("rejects missing full_name", () => {
    const result = registerSchema.safeParse({
      email: "user@university.edu",
      password: "SecurePass1",
      full_name: "",
      role: "student",
      faculty: "ФКН",
    });
    expect(result.success).toBe(false);
  });

  it("rejects missing faculty", () => {
    const result = registerSchema.safeParse({
      email: "user@university.edu",
      password: "SecurePass1",
      full_name: "Іванов Іван",
      role: "student",
      faculty: "",
    });
    expect(result.success).toBe(false);
  });

  it("rejects year out of range", () => {
    const result = registerSchema.safeParse({
      email: "user@university.edu",
      password: "SecurePass1",
      full_name: "Іванов Іван",
      role: "student",
      faculty: "ФКН",
      year: 7,
    });
    expect(result.success).toBe(false);
  });
});
