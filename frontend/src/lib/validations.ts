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
    .min(8, "Password must be at least 8 characters")
    .regex(/[A-Z]/, "Password must contain at least one uppercase letter")
    .regex(/[a-z]/, "Password must contain at least one lowercase letter")
    .regex(/\d/, "Password must contain at least one digit"),
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

const passwordRules = z
  .string()
  .min(8, "Password must be at least 8 characters")
  .regex(/[A-Z]/, "Password must contain at least one uppercase letter")
  .regex(/[a-z]/, "Password must contain at least one lowercase letter")
  .regex(/\d/, "Password must contain at least one digit");

export const changePasswordSchema = z
  .object({
    current_password: z.string().min(1, "Current password is required"),
    new_password: passwordRules,
    confirm_password: z.string().min(1, "Password confirmation is required"),
  })
  .refine((data) => data.new_password === data.confirm_password, {
    message: "Passwords do not match",
    path: ["confirm_password"],
  });

export type ChangePasswordFormData = z.infer<typeof changePasswordSchema>;

export const forgotPasswordSchema = z.object({
  email: z
    .string()
    .min(1, "Email is required")
    .email("Invalid email format"),
});

export type ForgotPasswordFormData = z.infer<typeof forgotPasswordSchema>;

export const resetPasswordSchema = z
  .object({
    new_password: passwordRules,
    confirm_password: z.string().min(1, "Password confirmation is required"),
  })
  .refine((data) => data.new_password === data.confirm_password, {
    message: "Passwords do not match",
    path: ["confirm_password"],
  });

export type ResetPasswordFormData = z.infer<typeof resetPasswordSchema>;

export const profileUpdateSchema = z.object({
  full_name: z.string().min(1, "Full name is required"),
  faculty: z.string().min(1, "Faculty is required"),
  group: z.string().optional(),
  year: z.coerce.number().min(1).max(6).optional(),
  department: z.string().optional(),
  position: z.string().optional(),
});

export type ProfileUpdateFormData = z.infer<typeof profileUpdateSchema>;
