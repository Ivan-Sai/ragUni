"use client";

import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";
import { Plus, Pencil, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
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
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

import {
  useDictionaryMutations,
  useFaculties,
  useGroups,
} from "@/hooks/use-dictionaries";
import type { GroupResponse, StudyLevel } from "@/types/api";

const LEVELS: StudyLevel[] = ["bachelor", "master", "phd"];

/**
 * Group CRUD section.
 *
 * The "Filter by faculty" select doubles as a navigation aid (the
 * group list can grow to hundreds) and as the default faculty for
 * newly created groups — admins almost always create several groups
 * for the same faculty in a row.
 */
export function GroupSection({ refreshKey }: { refreshKey: number }) {
  const t = useTranslations("admin.dictionaries");
  const tCommon = useTranslations("common");
  const faculties = useFaculties();
  const mutations = useDictionaryMutations();

  const [filterFacultyId, setFilterFacultyId] = useState<string>("");
  const groups = useGroups(filterFacultyId || null);

  // The hook caches per-(faculty_id, level) pair, but the dictionary
  // page mutates them in-place. ``refreshKey`` from the parent forces
  // a refetch every time the faculty section changes.
  useEffect(() => {
    if (filterFacultyId) {
      void groups.refetch();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey, filterFacultyId]);

  const [editing, setEditing] = useState<GroupResponse | null>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [facultyId, setFacultyId] = useState<string>("");
  const [level, setLevel] = useState<StudyLevel | "">("");
  const [busy, setBusy] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<GroupResponse | null>(null);

  const sortedFaculties = useMemo(
    () => [...faculties.items].sort((a, b) => a.name.localeCompare(b.name)),
    [faculties.items],
  );

  // Base UI's <Select.Value> renders the raw value unless it can look
  // the label up from a value→label map on the root. We feed every
  // ObjectId-valued select with this map so the trigger displays the
  // human-readable group / faculty name.
  const facultyLabels = useMemo(
    () =>
      sortedFaculties.reduce<Record<string, string>>((acc, f) => {
        acc[f.id] = f.name;
        return acc;
      }, {}),
    [sortedFaculties],
  );
  // Same trick for the study-level select — without this map the
  // trigger shows the raw enum value ("bachelor") instead of the
  // localised label ("Бакалавр").
  const levelLabels: Record<string, string> = {
    bachelor: t("level.bachelor"),
    master: t("level.master"),
    phd: t("level.phd"),
  };

  function openCreate() {
    setName("");
    setFacultyId(filterFacultyId || "");
    setLevel("");
    setEditing(null);
    setCreating(true);
  }

  function openEdit(group: GroupResponse) {
    setName(group.name);
    setFacultyId(group.faculty_id);
    setLevel(group.level);
    setEditing(group);
    setCreating(false);
  }

  function closeDialog() {
    setCreating(false);
    setEditing(null);
  }

  async function handleSave() {
    if (!name.trim() || !facultyId || !level) {
      toast.error(t("groupFieldsRequired"));
      return;
    }
    setBusy(true);
    try {
      if (editing) {
        await mutations.updateGroup(editing.id, {
          name: name.trim(),
          faculty_id: facultyId,
          level,
        });
        toast.success(t("groupUpdated"));
      } else {
        await mutations.createGroup({
          name: name.trim(),
          faculty_id: facultyId,
          level,
        });
        toast.success(t("groupCreated"));
      }
      await groups.refetch();
      closeDialog();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : tCommon("unknownError"));
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    setBusy(true);
    try {
      await mutations.deleteGroup(deleteTarget.id);
      toast.success(t("groupDeleted"));
      await groups.refetch();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : tCommon("unknownError"));
    } finally {
      setBusy(false);
      setDeleteTarget(null);
    }
  }

  const canCreate = sortedFaculties.length > 0;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-4">
        <div>
          <CardTitle>{t("groupsTitle")}</CardTitle>
          <CardDescription>{t("groupsDescription")}</CardDescription>
        </div>
        <Button size="sm" onClick={openCreate} disabled={!canCreate}>
          <Plus className="mr-2 h-4 w-4" />
          {t("addGroup")}
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-2">
          <Label className="text-sm font-medium">{t("filterByFaculty")}</Label>
          <Select
            value={filterFacultyId}
            onValueChange={(v) => setFilterFacultyId(v ?? "")}
            items={facultyLabels}
            disabled={sortedFaculties.length === 0}
          >
            <SelectTrigger className="w-72">
              <SelectValue
                placeholder={
                  sortedFaculties.length === 0
                    ? t("noFacultiesYet")
                    : t("filterAllFaculties")
                }
              />
            </SelectTrigger>
            <SelectContent>
              {sortedFaculties.map((f) => (
                <SelectItem key={f.id} value={f.id}>
                  {f.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {sortedFaculties.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {t("noFacultiesPrompt")}
          </p>
        ) : !filterFacultyId ? (
          <p className="text-sm text-muted-foreground">
            {t("filterPickPrompt")}
          </p>
        ) : groups.isLoading ? (
          <p className="text-sm text-muted-foreground">{tCommon("loading")}</p>
        ) : groups.items.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("groupsEmpty")}</p>
        ) : (
          <ul className="divide-y">
            {groups.items.map((group) => (
              <li
                key={group.id}
                className="flex items-center justify-between py-2"
              >
                <div className="flex items-center gap-3">
                  <span className="text-sm font-medium">{group.name}</span>
                  <span className="rounded bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                    {t(`level.${group.level}`)}
                  </span>
                </div>
                <div className="flex gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => openEdit(group)}
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setDeleteTarget(group)}
                  >
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>

      {/* Create / edit dialog */}
      <Dialog
        open={creating || !!editing}
        onOpenChange={(open) => {
          if (!open) closeDialog();
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {editing ? t("editGroup") : t("addGroup")}
            </DialogTitle>
            <DialogDescription>{t("groupDialogHint")}</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-2">
              <Label>{t("facultyName")}</Label>
              <Select
                value={facultyId}
                onValueChange={(v) => setFacultyId(v ?? "")}
                items={facultyLabels}
              >
                <SelectTrigger>
                  <SelectValue placeholder={t("filterAllFaculties")} />
                </SelectTrigger>
                <SelectContent>
                  {sortedFaculties.map((f) => (
                    <SelectItem key={f.id} value={f.id}>
                      {f.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>{t("groupLevel")}</Label>
              <Select
                value={level}
                onValueChange={(v) => setLevel(v as StudyLevel)}
                items={levelLabels}
              >
                <SelectTrigger>
                  <SelectValue placeholder={t("groupLevelPlaceholder")} />
                </SelectTrigger>
                <SelectContent>
                  {LEVELS.map((lvl) => (
                    <SelectItem key={lvl} value={lvl}>
                      {t(`level.${lvl}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="group-name">{t("groupName")}</Label>
              <Input
                id="group-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t("groupNamePlaceholder")}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={closeDialog} disabled={busy}>
              {tCommon("cancel")}
            </Button>
            <Button onClick={handleSave} disabled={busy}>
              {tCommon("save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete confirmation */}
      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("deleteGroupTitle")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("deleteGroupDescription", {
                name: deleteTarget?.name ?? "",
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>
              {tCommon("cancel")}
            </AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} disabled={busy}>
              {tCommon("delete")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
