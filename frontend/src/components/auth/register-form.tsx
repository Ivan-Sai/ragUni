"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { toast } from "sonner";
import { useTranslations } from "next-intl";
import { authApi } from "@/lib/api";
import { registerSchema } from "@/lib/validations";
import { mapZodErrors } from "@/lib/validation-i18n";
import { usePublicFaculties, usePublicGroups } from "@/hooks/use-dictionaries";
import type { StudyLevel } from "@/types/api";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

type RoleChoice = "student" | "teacher";

export function RegisterForm() {
  const router = useRouter();
  const t = useTranslations("auth.register");
  const tValidation = useTranslations("auth.validation");
  const tCommon = useTranslations("common");

  const [role, setRole] = useState<RoleChoice>("student");
  const [facultyId, setFacultyId] = useState<string>("");
  const [groupId, setGroupId] = useState<string>("");
  const [level, setLevel] = useState<StudyLevel | "">("");
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);

  // Faculty list is the same for everyone — read it without a token.
  const faculties = usePublicFaculties();
  // Groups depend on the chosen faculty AND (for students) the chosen
  // study level. Re-running on either change keeps the dropdown
  // strictly consistent with the rest of the form.
  const groups = usePublicGroups(
    role === "student" && facultyId ? facultyId : null,
    role === "student" && level ? level : null,
  );

  // Base UI Select needs a value→label map on the root to render
  // labels in the trigger; without it `<Select.Value>` shows the raw
  // ObjectId. We rebuild the maps from the live dictionary.
  const facultyLabels = useMemo(
    () =>
      faculties.items.reduce<Record<string, string>>((acc, f) => {
        acc[f.id] = f.name;
        return acc;
      }, {}),
    [faculties.items],
  );
  const groupLabels = useMemo(
    () =>
      groups.items.reduce<Record<string, string>>((acc, g) => {
        acc[g.id] = g.name;
        return acc;
      }, {}),
    [groups.items],
  );
  // Same idea for the role and study-level enums — Select renders the
  // raw value ("student" / "bachelor") in the trigger unless given a
  // value→label map.
  const roleLabels: Record<string, string> = {
    student: t("roleStudent"),
    teacher: t("roleTeacher"),
  };
  const levelLabels: Record<string, string> = {
    bachelor: t("levelBachelor"),
    master: t("levelMaster"),
    phd: t("levelPhd"),
  };

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    setFieldErrors({});

    const formData = new FormData(e.currentTarget);

    const email = formData.get("email");
    const password = formData.get("password");
    const full_name = formData.get("full_name");

    const rawData = {
      email: typeof email === "string" ? email : "",
      password: typeof password === "string" ? password : "",
      full_name: typeof full_name === "string" ? full_name : "",
      role,
      faculty_id: facultyId,
      group_id: role === "student" ? groupId : undefined,
      year:
        role === "student"
          ? Number.isFinite(Number(formData.get("year")))
            ? Number(formData.get("year"))
            : undefined
          : undefined,
      level: role === "student" && level ? level : undefined,
      department:
        role === "teacher"
          ? (formData.get("department") as string) || undefined
          : undefined,
      position:
        role === "teacher"
          ? (formData.get("position") as string) || undefined
          : undefined,
    };

    const validation = registerSchema.safeParse(rawData);
    if (!validation.success) {
      setFieldErrors(mapZodErrors(validation.error.issues, tValidation));
      return;
    }

    setLoading(true);
    try {
      await authApi.register(validation.data);
      toast.success(t("success"));
      setTimeout(() => {
        router.push("/login");
      }, 1000);
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
            <PasswordInput
              id="password"
              name="password"
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
              onValueChange={(v) => {
                setRole((v ?? "student") as RoleChoice);
                // Reset role-dependent selections so the form stays
                // consistent — a teacher does not need group / level.
                setGroupId("");
                setLevel("");
              }}
              items={roleLabels}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="student">{t("roleStudent")}</SelectItem>
                <SelectItem value="teacher">{t("roleTeacher")}</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="faculty_id">{t("faculty")}</Label>
            <Select
              value={facultyId}
              onValueChange={(v) => {
                setFacultyId(v ?? "");
                // Group depends on faculty — a stale group_id from the
                // previous faculty would either fail validation or
                // sneak through. Drop it on every faculty change.
                setGroupId("");
              }}
              items={facultyLabels}
              disabled={faculties.isLoading || faculties.items.length === 0}
            >
              <SelectTrigger
                id="faculty_id"
                aria-invalid={!!fieldErrors.faculty_id}
              >
                <SelectValue
                  placeholder={
                    faculties.isLoading
                      ? tCommon("loading") || "..."
                      : t("facultyPlaceholder")
                  }
                />
              </SelectTrigger>
              <SelectContent>
                {faculties.items.map((f) => (
                  <SelectItem key={f.id} value={f.id}>
                    {f.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {fieldErrors.faculty_id && (
              <p className="text-sm text-destructive">
                {fieldErrors.faculty_id}
              </p>
            )}
            {faculties.error && (
              <p className="text-sm text-destructive">{faculties.error}</p>
            )}
          </div>

          {role === "student" && (
            <>
              <div className="space-y-2">
                <Label htmlFor="level">{t("level")}</Label>
                <Select
                  value={level}
                  onValueChange={(v) => {
                    setLevel((v ?? "") as StudyLevel | "");
                    // Group list is filtered by level — reset.
                    setGroupId("");
                  }}
                  items={levelLabels}
                >
                  <SelectTrigger
                    id="level"
                    aria-invalid={!!fieldErrors.level}
                  >
                    <SelectValue placeholder={t("levelPlaceholder")} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="bachelor">{t("levelBachelor")}</SelectItem>
                    <SelectItem value="master">{t("levelMaster")}</SelectItem>
                    <SelectItem value="phd">{t("levelPhd")}</SelectItem>
                  </SelectContent>
                </Select>
                {fieldErrors.level && (
                  <p className="text-sm text-destructive">{fieldErrors.level}</p>
                )}
              </div>

              <div className="space-y-2">
                <Label htmlFor="group_id">{t("group")}</Label>
                <Select
                  value={groupId}
                  onValueChange={(v) => setGroupId(v ?? "")}
                  items={groupLabels}
                  disabled={!facultyId || !level || groups.isLoading}
                >
                  <SelectTrigger
                    id="group_id"
                    aria-invalid={!!fieldErrors.group_id}
                  >
                    <SelectValue
                      placeholder={
                        !facultyId || !level
                          ? t("groupPickFacultyAndLevel")
                          : groups.isLoading
                            ? tCommon("loading") || "..."
                            : groups.items.length === 0
                              ? t("groupEmpty")
                              : t("groupPlaceholder")
                      }
                    />
                  </SelectTrigger>
                  <SelectContent>
                    {groups.items.map((g) => (
                      <SelectItem key={g.id} value={g.id}>
                        {g.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {fieldErrors.group_id && (
                  <p className="text-sm text-destructive">
                    {fieldErrors.group_id}
                  </p>
                )}
                {groups.error && (
                  <p className="text-sm text-destructive">{groups.error}</p>
                )}
              </div>

              <div className="space-y-2">
                <Label htmlFor="year">{t("year")}</Label>
                <Input
                  id="year"
                  name="year"
                  type="number"
                  min={1}
                  max={6}
                  placeholder={t("yearPlaceholder")}
                  aria-invalid={!!fieldErrors.year}
                />
                {fieldErrors.year && (
                  <p className="text-sm text-destructive">{fieldErrors.year}</p>
                )}
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

          <p className="rounded-md border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
            {t("approvalNotice")}
          </p>
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
