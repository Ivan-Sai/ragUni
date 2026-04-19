"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { toast } from "sonner";
import { useTranslations } from "next-intl";
import { resetPasswordSchema } from "@/lib/validations";
import { mapZodErrors } from "@/lib/validation-i18n";
import { authApi } from "@/lib/api";
import { Button } from "@/components/ui/button";
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

function ResetPasswordContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token") || "";
  const t = useTranslations("auth.resetPassword");
  const tValidation = useTranslations("auth.validation");

  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  if (!token) {
    return (
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>{t("invalidLinkTitle")}</CardTitle>
          <CardDescription>
            {t("invalidLinkDescription")}
          </CardDescription>
        </CardHeader>
        <CardFooter>
          <Link
            href="/forgot-password"
            className="text-sm text-primary underline"
          >
            {t("requestNewLink")}
          </Link>
        </CardFooter>
      </Card>
    );
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setFieldErrors({});

    const validation = resetPasswordSchema.safeParse({
      new_password: newPassword,
      confirm_password: confirmPassword,
    });
    if (!validation.success) {
      setFieldErrors(mapZodErrors(validation.error.issues, tValidation));
      return;
    }

    setLoading(true);
    try {
      await authApi.resetPassword({ token, new_password: newPassword });
      setDone(true);
      toast.success(t("successToast"));
    } catch (err) {
      const message =
        err instanceof Error ? err.message : t("serverError");
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  if (done) {
    return (
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>{t("doneTitle")}</CardTitle>
          <CardDescription>
            {t("doneDescription")}
          </CardDescription>
        </CardHeader>
        <CardFooter>
          <Link href="/login" className="text-sm text-primary underline">
            {t("login")}
          </Link>
        </CardFooter>
      </Card>
    );
  }

  return (
    <Card className="w-full max-w-md">
      <CardHeader>
        <CardTitle>{t("title")}</CardTitle>
        <CardDescription>
          {t("description")}
        </CardDescription>
      </CardHeader>
      <form onSubmit={handleSubmit} noValidate>
        <CardContent className="space-y-4 pb-2">
          {error && (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          )}
          <div className="space-y-2">
            <Label htmlFor="new_password">{t("newPassword")}</Label>
            <PasswordInput
              id="new_password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              aria-invalid={!!fieldErrors.new_password}
            />
            {fieldErrors.new_password && (
              <p className="text-sm text-destructive">
                {fieldErrors.new_password}
              </p>
            )}
          </div>
          <div className="space-y-2">
            <Label htmlFor="confirm_password">{t("confirmPassword")}</Label>
            <PasswordInput
              id="confirm_password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              aria-invalid={!!fieldErrors.confirm_password}
            />
            {fieldErrors.confirm_password && (
              <p className="text-sm text-destructive">
                {fieldErrors.confirm_password}
              </p>
            )}
          </div>
        </CardContent>
        <CardFooter className="flex flex-col gap-3">
          <Button type="submit" className="w-full" disabled={loading}>
            {t("submit")}
          </Button>
        </CardFooter>
      </form>
    </Card>
  );
}

export default function ResetPasswordPage() {
  const t = useTranslations("auth.resetPassword");
  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Suspense
        fallback={
          <Card className="w-full max-w-md">
            <CardHeader>
              <CardTitle>{t("loading")}</CardTitle>
            </CardHeader>
          </Card>
        }
      >
        <ResetPasswordContent />
      </Suspense>
    </div>
  );
}
