"use client";

import { useState } from "react";
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
} from "@/hooks/use-dictionaries";
import type { FacultyResponse } from "@/types/api";

/**
 * Faculty CRUD section.
 *
 * Bubbles every change to ``onChanged`` so the sibling group section
 * can reload its dropdown without reading our state directly. The
 * delete dialog refuses to act when the API returns 409 (faculty has
 * dependants) — the toast surfaces the backend's reason verbatim.
 */
export function FacultySection({ onChanged }: { onChanged: () => void }) {
  const t = useTranslations("admin.dictionaries");
  const tCommon = useTranslations("common");
  const { items, isLoading, error, refetch } = useFaculties();
  const mutations = useDictionaryMutations();

  const [editing, setEditing] = useState<FacultyResponse | null>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<FacultyResponse | null>(null);

  function openCreate() {
    setName("");
    setEditing(null);
    setCreating(true);
  }

  function openEdit(faculty: FacultyResponse) {
    setName(faculty.name);
    setEditing(faculty);
    setCreating(false);
  }

  function closeDialog() {
    setCreating(false);
    setEditing(null);
    setName("");
  }

  async function handleSave() {
    if (!name.trim()) {
      toast.error(t("nameRequired"));
      return;
    }
    setBusy(true);
    try {
      if (editing) {
        await mutations.updateFaculty(editing.id, { name: name.trim() });
        toast.success(t("facultyUpdated"));
      } else {
        await mutations.createFaculty({ name: name.trim() });
        toast.success(t("facultyCreated"));
      }
      await refetch();
      onChanged();
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
      await mutations.deleteFaculty(deleteTarget.id);
      toast.success(t("facultyDeleted"));
      await refetch();
      onChanged();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : tCommon("unknownError"));
    } finally {
      setBusy(false);
      setDeleteTarget(null);
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle>{t("facultiesTitle")}</CardTitle>
          <CardDescription>{t("facultiesDescription")}</CardDescription>
        </div>
        <Button size="sm" onClick={openCreate}>
          <Plus className="mr-2 h-4 w-4" />
          {t("addFaculty")}
        </Button>
      </CardHeader>
      <CardContent>
        {error && (
          <p className="mb-2 text-sm text-destructive">{error}</p>
        )}
        {isLoading ? (
          <p className="text-sm text-muted-foreground">{tCommon("loading")}</p>
        ) : items.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {t("facultiesEmpty")}
          </p>
        ) : (
          <ul className="divide-y">
            {items.map((faculty) => (
              <li
                key={faculty.id}
                className="flex items-center justify-between py-2"
              >
                <span className="text-sm font-medium">{faculty.name}</span>
                <div className="flex gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => openEdit(faculty)}
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setDeleteTarget(faculty)}
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
              {editing ? t("editFaculty") : t("addFaculty")}
            </DialogTitle>
            <DialogDescription>{t("facultyDialogHint")}</DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="faculty-name">{t("facultyName")}</Label>
            <Input
              id="faculty-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("facultyNamePlaceholder")}
              autoFocus
            />
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
            <AlertDialogTitle>{t("deleteFacultyTitle")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("deleteFacultyDescription", {
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
