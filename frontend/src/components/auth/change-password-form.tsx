"use client";

import { useState } from "react";
import { useSession } from "next-auth/react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";
import { changePasswordSchema } from "@/lib/validations";
import { mapZodErrors } from "@/lib/validation-i18n";
import { authApi } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { PasswordInput } from "@/components/ui/password-input";
import { Label } from "@/components/ui/label";

export function ChangePasswordForm() {
  const { data: session } = useSession();
  const t = useTranslations("auth.changePassword");
  const tValidation = useTranslations("auth.validation");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setFieldErrors({});

    const validation = changePasswordSchema.safeParse({
      current_password: currentPassword,
      new_password: newPassword,
      confirm_password: confirmPassword,
    });
    if (!validation.success) {
      setFieldErrors(mapZodErrors(validation.error.issues, tValidation));
      return;
    }

    const token = session?.accessToken;
    if (!token) return;

    setLoading(true);
    try {
      await authApi.changePassword(
        { current_password: currentPassword, new_password: newPassword },
        token
      );
      toast.success(t("success"));
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err) {
      const message =
        err instanceof Error ? err.message : t("serverError");
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4" noValidate>
      {error && (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      )}
      <div className="space-y-2">
        <Label htmlFor="current_password">{t("currentPassword")}</Label>
        <PasswordInput
          id="current_password"
          value={currentPassword}
          onChange={(e) => setCurrentPassword(e.target.value)}
          aria-invalid={!!fieldErrors.current_password}
        />
        {fieldErrors.current_password && (
          <p className="text-sm text-destructive">
            {fieldErrors.current_password}
          </p>
        )}
      </div>
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
      <Button type="submit" disabled={loading}>
        {t("submit")}
      </Button>
    </form>
  );
}
