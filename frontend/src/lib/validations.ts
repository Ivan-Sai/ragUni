import { z } from "zod";

export const loginSchema = z.object({
  email: z
    .string()
    .min(1, "Email is required")
    .email("Invalid email format"),
  password: z
    .string()
    .min(1, "Password is required")
    .min(8, "Password must be at least 8 characters"),
});

export type LoginFormData = z.infer<typeof loginSchema>;

export const registerSchema = z.object({
  email: z
    .string()
    .min(1, "Email is required")
    .email("Invalid email format"),
  password: z
    .string()
    .min(1, "Password is required")
    .min(8, "Password must be at least 8 characters"),
  full_name: z
    .string()
    .min(1, "Full name is required"),
  role: z.enum(["student", "teacher"]),
  faculty: z
    .string()
    .min(1, "Faculty is required"),
  group: z.string().optional(),
  year: z.coerce.number().min(1).max(6).optional(),
  department: z.string().optional(),
  position: z.string().optional(),
});

export type RegisterFormData = z.infer<typeof registerSchema>;
