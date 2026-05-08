"use client";

import { useEffect, useMemo, useState } from "react";
import { useSession } from "next-auth/react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";

import { adminApi } from "@/lib/api";
import { useFaculties, useGroups } from "@/hooks/use-dictionaries";
import type {
  AdminUserUpdateData,
  StudyLevel,
  UserResponse,
} from "@/types/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface AdminUserEditDialogProps {
  user: UserResponse | null;
  onClose: () => void;
  onSaved: () => void;
}

/**
 * Admin-only user editor.
 *
 * Lets the admin correct any user's faculty, group, study level and
 * year. The cascading select mirrors the registration form so the
 * stored value is always consistent (group ↔ faculty ↔ level).
 */
export function AdminUserEditDialog({
  user,
  onClose,
  onSaved,
}: AdminUserEditDialogProps) {
  const { data: session } = useSession();
  const t = useTranslations("admin.users");
  const tDict = useTranslations("admin.dictionaries");
  const tCommon = useTranslations("common");
  const token = session?.accessToken || "";

  const [fullName, setFullName] = useState("");
  const [facultyId, setFacultyId] = useState<string>("");
  const [level, setLevel] = useState<StudyLevel | "">("");
  const [groupId, setGroupId] = useState<string>("");
  const [year, setYear] = useState<string>("");
  const [department, setDepartment] = useState<string>("");
  const [position, setPosition] = useState<string>("");
  const [busy, setBusy] = useState(false);

  const faculties = useFaculties();
  const groups = useGroups(facultyId || null, level || null);

  // Value→label maps. Base UI Select renders the raw value in the
  // trigger unless the root receives a value-keyed label dictionary.
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
  const levelLabels: Record<string, string> = {
    bachelor: tDict("level.bachelor"),
    master: tDict("level.master"),
    phd: tDict("level.phd"),
  };

  // Hydrate the form whenever a new user is opened. Done in an effect
  // (not a derived value) so admin's edits survive the dialog being
  // re-opened later without losing focus on every render.
  useEffect(() => {
    if (!user) return;
    setFullName(user.full_name || "");
    setFacultyId(user.faculty_id || "");
    setLevel(user.level || "");
    setGroupId(user.group_id || "");
    setYear(user.year ? String(user.year) : "");
    setDepartment(user.department || "");
    setPosition(user.position || "");
  }, [user]);

  // Drop a stale group_id when faculty / level change so the admin
  // cannot save an inconsistent triple.
  useEffect(() => {
    if (!user) return;
    if (
      user.faculty_id !== facultyId ||
      (user.level || "") !== level
    ) {
      setGroupId("");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [facultyId, level]);

  if (!user) return null;
  const isStudent = user.role === "student";

  async function handleSave() {
    if (!user) return;
    const payload: AdminUserUpdateData = {};
    if (fullName !== user.full_name) payload.full_name = fullName;
    if (facultyId && facultyId !== user.faculty_id) {
      payload.faculty_id = facultyId;
    }
    if (isStudent) {
      if (groupId && groupId !== user.group_id) payload.group_id = groupId;
      if (year && Number(year) !== user.year) payload.year = Number(year);
      if (level && level !== user.level) payload.level = level;
    } else {
      if (department !== (user.department || "")) {
        payload.department = department;
      }
      if (position !== (user.position || "")) {
        payload.position = position;
      }
    }

    if (Object.keys(payload).length === 0) {
      toast.info(tCommon("save"));
      onClose();
      return;
    }

    setBusy(true);
    try {
      await adminApi.updateUser(user.id, payload, token);
      toast.success(t("editSuccess"));
      onSaved();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : tCommon("unknownError"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={!!user}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>
            {t("editTitle", { name: user.full_name || user.email })}
          </DialogTitle>
          <DialogDescription>{t("editDescription")}</DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-2">
          <div className="space-y-1.5">
            <Label htmlFor="edit-full-name">{t("name")}</Label>
            <Input
              id="edit-full-name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
            />
          </div>

          <div className="space-y-1.5">
            <Label>{t("faculty")}</Label>
            <Select
              value={facultyId}
              onValueChange={(v) => setFacultyId(v ?? "")}
              items={facultyLabels}
            >
              <SelectTrigger>
                <SelectValue placeholder="—" />
              </SelectTrigger>
              <SelectContent>
                {faculties.items.map((f) => (
                  <SelectItem key={f.id} value={f.id}>
                    {f.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {isStudent && (
            <>
              <div className="space-y-1.5">
                <Label>{tDict("groupLevel")}</Label>
                <Select
                  value={level}
                  onValueChange={(v) => setLevel((v ?? "") as StudyLevel | "")}
                  items={levelLabels}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="—" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="bachelor">
                      {tDict("level.bachelor")}
                    </SelectItem>
                    <SelectItem value="master">
                      {tDict("level.master")}
                    </SelectItem>
                    <SelectItem value="phd">{tDict("level.phd")}</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label>{t("group")}</Label>
                <Select
                  value={groupId}
                  onValueChange={(v) => setGroupId(v ?? "")}
                  items={groupLabels}
                  disabled={!facultyId || !level}
                >
                  <SelectTrigger>
                    <SelectValue
                      placeholder={
                        !facultyId || !level
                          ? "—"
                          : groups.isLoading
                            ? tCommon("loading")
                            : "—"
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
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="edit-year">{t("year")}</Label>
                <Input
                  id="edit-year"
                  type="number"
                  min={1}
                  max={6}
                  value={year}
                  onChange={(e) => setYear(e.target.value)}
                />
              </div>
            </>
          )}

          {!isStudent && (
            <>
              <div className="space-y-1.5">
                <Label htmlFor="edit-department">{t("department")}</Label>
                <Input
                  id="edit-department"
                  value={department}
                  onChange={(e) => setDepartment(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="edit-position">{t("position")}</Label>
                <Input
                  id="edit-position"
                  value={position}
                  onChange={(e) => setPosition(e.target.value)}
                />
              </div>
            </>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>
            {tCommon("cancel")}
          </Button>
          <Button onClick={handleSave} disabled={busy}>
            {tCommon("save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
