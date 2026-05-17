"use client";

import { useState, useEffect } from "react";
import { useSession } from "next-auth/react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";
import { Lock } from "lucide-react";

import { authApi } from "@/lib/api";
import type { ProfileUpdateData, UserResponse } from "@/types/api";
import { profileUpdateSchema } from "@/lib/validations";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/**
 * Profile editor.
 *
 * Dictionary fields (faculty / group / year / level) are shown for
 * read-only context but cannot be edited self-service — only an admin
 * can change them via /admin/users/{id}. We display them with a small
 * lock icon and a hint banner so users know who to contact.
 */
export function ProfileForm() {
  const { data: session } = useSession();
  const t = useTranslations("profile.form");
  const tDict = useTranslations("admin.dictionaries");
  const token = session?.accessToken || "";
  const role = session?.user?.role;

  const [user, setUser] = useState<UserResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const [fullName, setFullName] = useState("");
  const [department, setDepartment] = useState("");
  const [position, setPosition] = useState("");

  useEffect(() => {
    if (!token) return;
    authApi
      .getMe(token)
      .then((u) => {
        setUser(u);
        setFullName(u.full_name);
        setDepartment(u.department || "");
        setPosition(u.position || "");
      })
      .catch(() => setError(t("loadError")))
      .finally(() => setLoading(false));
  }, [token, t]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!token) return;
    setError("");
    setSaving(true);

    // Build a typed diff payload — only include fields the user
    // actually changed, mirroring the backend's "noChanges" guard.
    const data: ProfileUpdateData = {};
    if (fullName !== user?.full_name) data.full_name = fullName;
    if (role === "teacher" || role === "admin") {
      if (department !== (user?.department || "")) data.department = department;
      if (position !== (user?.position || "")) data.position = position;
    }

    if (Object.keys(data).length === 0) {
      setError(t("noChanges"));
      setSaving(false);
      return;
    }

    // Run client-side validation BEFORE the network call so the user
    // gets an immediate error on too-long values instead of a 422
    // round-trip. The Zod schema mirrors the backend caps.
    const parsed = profileUpdateSchema.safeParse(data);
    if (!parsed.success) {
      const firstIssue = parsed.error.issues[0];
      setError(firstIssue?.message ?? t("validationError"));
      setSaving(false);
      return;
    }

    try {
      const updated = await authApi.updateProfile(parsed.data, token);
      setUser(updated);
      toast.success(t("success"));
    } catch (err) {
      const message = err instanceof Error ? err.message : t("serverError");
      setError(message);
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <p className="text-muted-foreground">{t("loading")}</p>;
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4" noValidate>
      {error && (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      )}

      <div className="space-y-2">
        <Label htmlFor="email">{t("email")}</Label>
        <Input id="email" value={user?.email || ""} disabled />
      </div>

      <div className="space-y-2">
        <Label htmlFor="role">{t("role")}</Label>
        <Input
          id="role"
          value={
            user?.role === "student"
              ? t("roleStudent")
              : user?.role === "teacher"
                ? t("roleTeacher")
                : user?.role === "admin"
                  ? t("roleAdmin")
                  : user?.role || ""
          }
          disabled
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="full_name">{t("fullName")}</Label>
        <Input
          id="full_name"
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
        />
      </div>

      {role !== "admin" && (
        <div className="rounded-md border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
          <Lock className="mr-1 inline h-3 w-3" />
          {t("lockedFieldsHint")}
        </div>
      )}

      <div className="space-y-2">
        <Label htmlFor="faculty" className="flex items-center gap-1">
          <Lock className="h-3 w-3 text-muted-foreground" />
          {t("faculty")}
        </Label>
        <Input
          id="faculty"
          value={user?.faculty_name || ""}
          disabled
          aria-readonly
        />
      </div>

      {(role === "student" || (role === "admin" && user?.group_id)) && (
        <>
          <div className="space-y-2">
            <Label htmlFor="group" className="flex items-center gap-1">
              <Lock className="h-3 w-3 text-muted-foreground" />
              {t("group")}
            </Label>
            <Input
              id="group"
              value={user?.group_name || ""}
              disabled
              aria-readonly
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="year" className="flex items-center gap-1">
              <Lock className="h-3 w-3 text-muted-foreground" />
              {t("year")}
            </Label>
            <Input id="year" value={user?.year ?? ""} disabled aria-readonly />
          </div>
          <div className="space-y-2">
            <Label htmlFor="level" className="flex items-center gap-1">
              <Lock className="h-3 w-3 text-muted-foreground" />
              {t("level")}
            </Label>
            <Input
              id="level"
              value={user?.level ? tDict(`level.${user.level}`) : ""}
              disabled
              aria-readonly
            />
          </div>
        </>
      )}

      {(role === "teacher" || role === "admin") && (
        <>
          <div className="space-y-2">
            <Label htmlFor="department">{t("department")}</Label>
            <Input
              id="department"
              value={department}
              onChange={(e) => setDepartment(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="position">{t("position")}</Label>
            <Input
              id="position"
              value={position}
              onChange={(e) => setPosition(e.target.value)}
            />
          </div>
        </>
      )}

      <Button type="submit" disabled={saving}>
        {t("submit")}
      </Button>
    </form>
  );
}
