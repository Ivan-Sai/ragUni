"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { Upload, FileUp, X, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useFaculties, useGroups } from "@/hooks/use-dictionaries";
import type { DocumentUploadOptions, StudyLevel } from "@/types/api";

type AccessLevel = "public" | "faculty" | "restricted";

interface DocumentUploadProps {
  onUpload: (file: File, options: DocumentUploadOptions) => Promise<void>;
  isUploading: boolean;
}

const ALLOWED_TYPES = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "text/plain",
];

const ALLOWED_EXTENSIONS = ["pdf", "docx", "xlsx", "txt"];

const ALL_YEARS = [1, 2, 3, 4, 5, 6];

export function DocumentUpload({ onUpload, isUploading }: DocumentUploadProps) {
  const t = useTranslations("admin.upload");
  const tCommon = useTranslations("common");
  const tDict = useTranslations("admin.dictionaries");

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Audience targeting — every upload must specify at least the faculty.
  const [facultyId, setFacultyId] = useState<string>("");
  const [accessLevel, setAccessLevel] = useState<AccessLevel>("public");
  const [targetLevel, setTargetLevel] = useState<StudyLevel | "any">("any");
  const [targetGroupIds, setTargetGroupIds] = useState<string[]>([]);
  const [targetYears, setTargetYears] = useState<number[]>([]);

  // restricted = teachers/admins only. Audience targeting applies to
  // students, so it is meaningless (and confusing) when restricted.
  const audienceDisabled = accessLevel === "restricted";

  const faculties = useFaculties();
  const groups = useGroups(
    facultyId || null,
    targetLevel === "any" ? null : targetLevel,
  );

  // Value→label map so Base UI Select shows the faculty name in the
  // trigger instead of the raw ObjectId.
  const facultyLabels = useMemo(
    () =>
      faculties.items.reduce<Record<string, string>>((acc, f) => {
        acc[f.id] = f.name;
        return acc;
      }, {}),
    [faculties.items],
  );
  const levelLabels: Record<string, string> = {
    any: t("levelAny"),
    bachelor: tDict("level.bachelor"),
    master: tDict("level.master"),
    phd: tDict("level.phd"),
  };
  const accessLevelLabels: Record<string, string> = {
    public: t("accessLevelPublic"),
    faculty: t("accessLevelFaculty"),
    restricted: t("accessLevelRestricted"),
  };

  // Reset role-dependent picks when faculty / level change so a stale
  // group_id or wrong-level option cannot survive a re-pick.
  useEffect(() => {
    setTargetGroupIds([]);
  }, [facultyId, targetLevel]);

  // When switching to restricted (teachers/admins only), audience
  // targeting becomes meaningless — wipe it so we don't ship stale
  // student-level metadata with a teacher-only document.
  useEffect(() => {
    if (accessLevel === "restricted") {
      setTargetLevel("any");
      setTargetGroupIds([]);
      setTargetYears([]);
    }
  }, [accessLevel]);

  function validateFile(file: File): boolean {
    const ext = file.name.split(".").pop()?.toLowerCase();
    if (!ext || !ALLOWED_EXTENSIONS.includes(ext)) {
      setError(`${t("unsupportedFormat")}${ALLOWED_EXTENSIONS.join(", ")}`);
      return false;
    }
    if (file.type && !ALLOWED_TYPES.includes(file.type) && file.type !== "text/plain") {
      setError(`${t("mimeMismatch")}${ALLOWED_EXTENSIONS.join(", ")}`);
      return false;
    }
    if (file.size > 10 * 1024 * 1024) {
      setError(t("tooLarge"));
      return false;
    }
    setError(null);
    return true;
  }

  function handleFileSelect(file: File) {
    if (validateFile(file)) {
      setSelectedFile(file);
    }
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) handleFileSelect(file);
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setIsDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFileSelect(file);
  }

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault();
    setIsDragOver(true);
  }

  function handleDragLeave() {
    setIsDragOver(false);
  }

  function toggleGroup(id: string) {
    setTargetGroupIds((prev) =>
      prev.includes(id) ? prev.filter((g) => g !== id) : [...prev, id],
    );
  }

  function toggleYear(year: number) {
    setTargetYears((prev) =>
      prev.includes(year) ? prev.filter((y) => y !== year) : [...prev, year],
    );
  }

  async function handleUpload() {
    if (!selectedFile) return;
    if (!facultyId) {
      setError(t("facultyRequired"));
      return;
    }

    try {
      await onUpload(selectedFile, {
        facultyId,
        targetGroupIds: audienceDisabled ? [] : targetGroupIds,
        targetYears: audienceDisabled ? [] : targetYears,
        targetLevel:
          audienceDisabled || targetLevel === "any" ? null : targetLevel,
        accessLevel,
      });
      setSelectedFile(null);
      setError(null);
      setFacultyId("");
      setAccessLevel("public");
      setTargetLevel("any");
      setTargetGroupIds([]);
      setTargetYears([]);
      if (inputRef.current) inputRef.current.value = "";
    } catch (err) {
      setError(err instanceof Error ? err.message : t("errorDescription"));
    }
  }

  function handleClear() {
    setSelectedFile(null);
    setError(null);
    if (inputRef.current) inputRef.current.value = "";
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("title")}</CardTitle>
        <CardDescription>{t("description")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div
          className={`relative border-2 border-dashed rounded-lg p-6 text-center transition-colors ${
            isDragOver
              ? "border-primary bg-primary/5"
              : "border-muted-foreground/25"
          }`}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
        >
          {selectedFile ? (
            <div className="flex items-center justify-center gap-3">
              <FileUp className="h-5 w-5 text-muted-foreground" />
              <span className="text-sm font-medium">{selectedFile.name}</span>
              <span className="text-xs text-muted-foreground">
                ({Math.max(1, Math.round(selectedFile.size / 1024))} {tCommon("kb")})
              </span>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleClear}
                disabled={isUploading}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          ) : (
            <div className="space-y-2">
              <Upload className="mx-auto h-8 w-8 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">{t("dropzone")}</p>
            </div>
          )}

          <input
            ref={inputRef}
            type="file"
            accept={[...ALLOWED_TYPES, ".pdf", ".docx", ".xlsx", ".txt"].join(",")}
            onChange={handleInputChange}
            className={selectedFile ? "hidden" : "absolute inset-0 w-full h-full opacity-0 cursor-pointer"}
            style={selectedFile ? undefined : { position: "absolute", inset: 0 }}
          />
        </div>

        {error && <p className="text-sm text-red-500">{error}</p>}

        {selectedFile && (
          <>
            <div className="space-y-3 rounded-md border bg-muted/20 p-4">
              <div className="space-y-2">
                <Label className="text-xs">{t("accessLevelLabel")}</Label>
                <Select
                  value={accessLevel}
                  onValueChange={(v) =>
                    setAccessLevel((v ?? "public") as AccessLevel)
                  }
                  items={accessLevelLabels}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="public">
                      {t("accessLevelPublic")}
                    </SelectItem>
                    <SelectItem value="faculty">
                      {t("accessLevelFaculty")}
                    </SelectItem>
                    <SelectItem value="restricted">
                      {t("accessLevelRestricted")}
                    </SelectItem>
                  </SelectContent>
                </Select>
                {audienceDisabled && (
                  <p className="text-xs text-amber-600 dark:text-amber-400">
                    {t("accessLevelHintRestricted")}
                  </p>
                )}
              </div>

              <p className="text-xs text-muted-foreground">{t("audienceHint")}</p>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label className="text-xs">{t("facultyLabel")}</Label>
                  <Select
                    value={facultyId}
                    onValueChange={(v) => setFacultyId(v ?? "")}
                    items={facultyLabels}
                    disabled={faculties.items.length === 0}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder={t("facultyPlaceholder")} />
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

                <div className="space-y-2">
                  <Label className="text-xs">{t("levelLabel")}</Label>
                  <Select
                    value={targetLevel}
                    onValueChange={(v) =>
                      setTargetLevel((v ?? "any") as StudyLevel | "any")
                    }
                    items={levelLabels}
                    disabled={audienceDisabled}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="any">{t("levelAny")}</SelectItem>
                      <SelectItem value="bachelor">{tDict("level.bachelor")}</SelectItem>
                      <SelectItem value="master">{tDict("level.master")}</SelectItem>
                      <SelectItem value="phd">{tDict("level.phd")}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs">
                  {t("groupsLabel")}
                  <span className="ml-1 font-normal text-muted-foreground">
                    {t("groupsHint")}
                  </span>
                </Label>
                {audienceDisabled ? (
                  <p className="text-xs text-muted-foreground italic">
                    {t("accessLevelRestricted")}
                  </p>
                ) : !facultyId ? (
                  <p className="text-xs text-muted-foreground">
                    {t("groupsPickFaculty")}
                  </p>
                ) : groups.isLoading ? (
                  <p className="text-xs text-muted-foreground">
                    {tCommon("loading")}
                  </p>
                ) : groups.items.length === 0 ? (
                  <p className="text-xs text-muted-foreground">
                    {t("groupsEmpty")}
                  </p>
                ) : (
                  <div className="flex flex-wrap gap-1.5">
                    {groups.items.map((g) => {
                      const active = targetGroupIds.includes(g.id);
                      return (
                        <button
                          type="button"
                          key={g.id}
                          onClick={() => toggleGroup(g.id)}
                          className={`rounded-full border px-3 py-1 text-xs transition-colors ${
                            active
                              ? "border-primary bg-primary text-primary-foreground"
                              : "border-border bg-background hover:bg-muted"
                          }`}
                        >
                          {g.name}
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs">
                  {t("yearsLabel")}
                  <span className="ml-1 font-normal text-muted-foreground">
                    {t("yearsHint")}
                  </span>
                </Label>
                {audienceDisabled ? (
                  <p className="text-xs text-muted-foreground italic">
                    {t("accessLevelRestricted")}
                  </p>
                ) : (
                  <div className="flex flex-wrap gap-1.5">
                    {ALL_YEARS.map((year) => {
                      const active = targetYears.includes(year);
                      return (
                        <button
                          type="button"
                          key={year}
                          onClick={() => toggleYear(year)}
                          className={`rounded-full border px-3 py-1 text-xs transition-colors ${
                            active
                              ? "border-primary bg-primary text-primary-foreground"
                              : "border-border bg-background hover:bg-muted"
                          }`}
                        >
                          {year}
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>

            {isUploading ? (
              <UploadProgress />
            ) : (
              <Button
                className="w-full"
                onClick={handleUpload}
                disabled={isUploading || !facultyId}
              >
                {t("upload")}
              </Button>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

/**
 * Live progress indicator while an upload is in flight. Mounted only
 * during ``isUploading`` so its own setInterval lifecycle is bound to
 * the upload, not to the parent component.
 *
 * The classifier picks the right extraction strategy automatically,
 * so the UI no longer needs to distinguish between "raw" and
 * "LLM-extracted" uploads. Progress messages step through the
 * pipeline stages as they unfold.
 */
function UploadProgress() {
  const t = useTranslations("admin.upload");
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    function tick() {
      setElapsed((seconds) => seconds + 1);
    }
    const interval = setInterval(tick, 1000);
    return () => clearInterval(interval);
  }, []);

  const message = (() => {
    if (elapsed < 3) return t("stageParse");
    if (elapsed < 8) return t("stageClassify");
    if (elapsed < 20) return t("stageExtract");
    if (elapsed < 60) return t("stageEmbed");
    return t("stageFinalising");
  })();

  return (
    <div className="rounded-md border bg-muted/40 px-4 py-3">
      <div className="flex items-center gap-2 text-sm font-medium">
        <Loader2 className="h-4 w-4 animate-spin text-primary" />
        <span>{message}</span>
        <span className="ml-auto text-xs tabular-nums text-muted-foreground">
          {elapsed}s
        </span>
      </div>
      <div className="mt-2 h-1 overflow-hidden rounded-full bg-muted">
        <div className="h-full w-1/3 animate-[uploadbar_1.4s_ease-in-out_infinite] rounded-full bg-primary" />
      </div>
    </div>
  );
}
