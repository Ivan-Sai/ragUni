"use client";

import { useState, useEffect } from "react";
import { useSession } from "next-auth/react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";
import { authApi } from "@/lib/api";
import type { UserResponse } from "@/types/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function ProfileForm() {
  const { data: session } = useSession();
  const t = useTranslations("profile.form");
  const token = session?.accessToken || "";
  const role = session?.user?.role;

  const [user, setUser] = useState<UserResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const [fullName, setFullName] = useState("");
  const [faculty, setFaculty] = useState("");
  const [group, setGroup] = useState("");
  const [year, setYear] = useState("");
  const [department, setDepartment] = useState("");
  const [position, setPosition] = useState("");

  useEffect(() => {
    if (!token) return;
    authApi
      .getMe(token)
      .then((u) => {
        setUser(u);
        setFullName(u.full_name);
        setFaculty(u.faculty || "");
        setGroup(u.group || "");
        setYear(u.year ? String(u.year) : "");
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

    const data: Record<string, string | number> = {};
    if (fullName !== user?.full_name) data.full_name = fullName;
    if (faculty !== (user?.faculty || "")) data.faculty = faculty;

    if (role === "student" || role === "admin") {
      if (group !== (user?.group || "")) data.group = group;
      if (year && Number(year) !== user?.year) data.year = Number(year);
    }
    if (role === "teacher" || role === "admin") {
      if (department !== (user?.department || "")) data.department = department;
      if (position !== (user?.position || "")) data.position = position;
    }

    if (Object.keys(data).length === 0) {
      setError(t("noChanges"));
      setSaving(false);
      return;
    }

    try {
      const updated = await authApi.updateProfile(data, token);
      setUser(updated);
      toast.success(t("success"));
    } catch (err) {
      const message =
        err instanceof Error ? err.message : t("serverError");
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
        <Input id="role" value={user?.role || ""} disabled />
      </div>
      <div className="space-y-2">
        <Label htmlFor="full_name">{t("fullName")}</Label>
        <Input
          id="full_name"
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="faculty">{t("faculty")}</Label>
        <Input
          id="faculty"
          value={faculty}
          onChange={(e) => setFaculty(e.target.value)}
        />
      </div>

      {(role === "student" || role === "admin") && (
        <>
          <div className="space-y-2">
            <Label htmlFor="group">{t("group")}</Label>
            <Input
              id="group"
              value={group}
              onChange={(e) => setGroup(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="year">{t("year")}</Label>
            <Input
              id="year"
              type="number"
              min={1}
              max={6}
              value={year}
              onChange={(e) => setYear(e.target.value)}
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
