"use client";

import { useState } from "react";
import { signIn } from "next-auth/react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { toast } from "sonner";
import { useTranslations } from "next-intl";
import { loginSchema } from "@/lib/validations";
import { mapZodErrors } from "@/lib/validation-i18n";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export function LoginForm() {
  const router = useRouter();
  const t = useTranslations("auth.login");
  const tValidation = useTranslations("auth.validation");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setFieldErrors({});

    const validation = loginSchema.safeParse({ email, password });
    if (!validation.success) {
      setFieldErrors(mapZodErrors(validation.error.issues, tValidation));
      return;
    }

    setLoading(true);

    try {
      const result = await signIn("credentials", {
        redirect: false,
        email,
        password,
      });

      if (result?.error) {
        setError(t("invalidCredentials"));
      } else if (result?.ok) {
        toast.success(t("success"));
        router.replace("/chat");
        router.refresh();
      }
    } catch {
      setError(t("serverError"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card className="w-full max-w-md">
      <CardHeader>
        <CardTitle>{t("title")}</CardTitle>
        <CardDescription>
          {t("description")}
        </CardDescription>
      </CardHeader>
      <form onSubmit={handleSubmit} method="POST" noValidate>
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
              type="email"
              placeholder="example@university.edu"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              aria-invalid={!!fieldErrors.email}
              aria-describedby={fieldErrors.email ? "email-error" : undefined}
            />
            {fieldErrors.email && (
              <p id="email-error" className="text-sm text-destructive">
                {fieldErrors.email}
              </p>
            )}
          </div>
          <div className="space-y-2">
            <Label htmlFor="password">{t("password")}</Label>
            <PasswordInput
              id="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-invalid={!!fieldErrors.password}
              aria-describedby={fieldErrors.password ? "password-error" : undefined}
            />
            {fieldErrors.password && (
              <p id="password-error" className="text-sm text-destructive">
                {fieldErrors.password}
              </p>
            )}
          </div>
        </CardContent>
        <CardFooter className="flex flex-col gap-3">
          <Button type="submit" className="w-full" disabled={loading}>
            {t("submit")}
          </Button>
          <Link
            href="/forgot-password"
            className="text-sm text-muted-foreground hover:text-primary underline"
          >
            {t("forgotPassword")}
          </Link>
          <p className="text-sm text-muted-foreground">
            {t("noAccount")}{" "}
            <Link href="/register" className="text-primary underline">
              {t("register")}
            </Link>
          </p>
        </CardFooter>
      </form>
    </Card>
  );
}
