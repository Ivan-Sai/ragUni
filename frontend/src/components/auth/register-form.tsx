"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { toast } from "sonner";
import { useTranslations } from "next-intl";
import { authApi } from "@/lib/api";
import { registerSchema } from "@/lib/validations";
import type { UserRole } from "@/types/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export function RegisterForm() {
  const router = useRouter();
  const t = useTranslations("auth.register");
  const tValidation = useTranslations("auth.validation");
  const [role, setRole] = useState<UserRole>("student");
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    setFieldErrors({});

    const formData = new FormData(e.currentTarget);

    const email = formData.get("email");
    if (typeof email !== "string" || !email) {
      setError(tValidation("emailRequired"));
      return;
    }

    const password = formData.get("password");
    if (typeof password !== "string" || !password) {
      setError(tValidation("passwordRequired"));
      return;
    }

    const full_name = formData.get("full_name");
    if (typeof full_name !== "string" || !full_name) {
      setError(tValidation("fullNameRequired"));
      return;
    }

    const faculty = formData.get("faculty");
    if (typeof faculty !== "string" || !faculty) {
      setError(tValidation("facultyRequired"));
      return;
    }

    const rawData = {
      email,
      password,
      full_name,
      role,
      faculty,
      group: role === "student" ? (formData.get("group") as string) || undefined : undefined,
      year: role === "student" ? (Number.isFinite(Number(formData.get("year"))) ? Number(formData.get("year")) : undefined) : undefined,
      department: role === "teacher" ? (formData.get("department") as string) || undefined : undefined,
      position: role === "teacher" ? (formData.get("position") as string) || undefined : undefined,
    };

    const validation = registerSchema.safeParse(rawData);
    if (!validation.success) {
      const errors: Record<string, string> = {};
      for (const issue of validation.error.issues) {
        const field = String(issue.path[0]);
        if (!errors[field]) {
          errors[field] = issue.message;
        }
      }
      setFieldErrors(errors);
      return;
    }

    setLoading(true);

    try {
      await authApi.register(rawData);
      toast.success(t("success"));
      router.push("/login");
    } catch (err) {
      if (err instanceof TypeError && err.message === "Failed to fetch") {
        setError(t("serverError"));
      } else {
        setError(err instanceof Error ? err.message : t("genericError"));
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card className="w-full max-w-md">
      <CardHeader>
        <CardTitle>{t("title")}</CardTitle>
        <CardDescription>{t("description")}</CardDescription>
      </CardHeader>
      <form onSubmit={handleSubmit} noValidate>
        <CardContent className="space-y-4 pb-2">
          {error && (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          )}

          <div className="space-y-2">
            <Label htmlFor="email">{t("email")}</Label>
            <Input
              id="email"
              name="email"
              type="email"
              placeholder="example@university.edu"
              aria-invalid={!!fieldErrors.email}
              aria-describedby={fieldErrors.email ? "reg-email-error" : undefined}
            />
            {fieldErrors.email && (
              <p id="reg-email-error" className="text-sm text-destructive">
                {fieldErrors.email}
              </p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="password">{t("password")}</Label>
            <Input
              id="password"
              name="password"
              type="password"
              aria-invalid={!!fieldErrors.password}
              aria-describedby={fieldErrors.password ? "reg-password-error" : undefined}
            />
            {fieldErrors.password && (
              <p id="reg-password-error" className="text-sm text-destructive">
                {fieldErrors.password}
              </p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="full_name">{t("fullName")}</Label>
            <Input
              id="full_name"
              name="full_name"
              placeholder={t("fullNamePlaceholder")}
              aria-invalid={!!fieldErrors.full_name}
              aria-describedby={fieldErrors.full_name ? "reg-name-error" : undefined}
            />
            {fieldErrors.full_name && (
              <p id="reg-name-error" className="text-sm text-destructive">
                {fieldErrors.full_name}
              </p>
            )}
          </div>

          <div className="space-y-2">
            <Label>{t("role")}</Label>
            <Select
              value={role}
              onValueChange={(v) => setRole(v as UserRole)}
            >
              <SelectTrigger>
                <SelectValue placeholder={role === "student" ? t("roleStudent") : t("roleTeacher")} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="student">{t("roleStudent")}</SelectItem>
                <SelectItem value="teacher">{t("roleTeacher")}</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="faculty">{t("faculty")}</Label>
            <Input
              id="faculty"
              name="faculty"
              placeholder={t("facultyPlaceholder")}
              aria-invalid={!!fieldErrors.faculty}
              aria-describedby={fieldErrors.faculty ? "reg-faculty-error" : undefined}
            />
            {fieldErrors.faculty && (
              <p id="reg-faculty-error" className="text-sm text-destructive">
                {fieldErrors.faculty}
              </p>
            )}
          </div>

          {role === "student" && (
            <>
              <div className="space-y-2">
                <Label htmlFor="group">{t("group")}</Label>
                <Input id="group" name="group" placeholder={t("groupPlaceholder")} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="year">{t("year")}</Label>
                <Input
                  id="year"
                  name="year"
                  type="number"
                  placeholder={t("yearPlaceholder")}
                />
              </div>
            </>
          )}

          {role === "teacher" && (
            <>
              <div className="space-y-2">
                <Label htmlFor="department">{t("department")}</Label>
                <Input
                  id="department"
                  name="department"
                  placeholder={t("departmentPlaceholder")}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="position">{t("position")}</Label>
                <Input
                  id="position"
                  name="position"
                  placeholder={t("positionPlaceholder")}
                />
              </div>
            </>
          )}
        </CardContent>
        <CardFooter className="flex flex-col gap-3">
          <Button type="submit" className="w-full" disabled={loading}>
            {t("submit")}
          </Button>
          <p className="text-sm text-muted-foreground">
            {t("hasAccount")}{" "}
            <Link href="/login" className="text-primary underline">
              {t("login")}
            </Link>
          </p>
        </CardFooter>
      </form>
    </Card>
  );
}
