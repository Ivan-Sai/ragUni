"use client";

import { useState, useRef } from "react";
import { useTranslations } from "next-intl";
import { Upload, FileUp, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

interface DocumentUploadProps {
  onUpload: (file: File) => Promise<void>;
  isUploading: boolean;
}

const ALLOWED_TYPES = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "text/plain",
];

const ALLOWED_EXTENSIONS = ["pdf", "docx", "xlsx", "txt"];

export function DocumentUpload({ onUpload, isUploading }: DocumentUploadProps) {
  const t = useTranslations("admin.upload");
  const tCommon = useTranslations("common");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function validateFile(file: File): boolean {
    const ext = file.name.split(".").pop()?.toLowerCase();
    if (!ext || !ALLOWED_EXTENSIONS.includes(ext)) {
      setError(`${t("unsupportedFormat")}${ALLOWED_EXTENSIONS.join(", ")}`);
      return false;
    }
    // Also validate MIME type when available (prevents renamed file spoofing)
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

  async function handleUpload() {
    if (!selectedFile) return;

    try {
      await onUpload(selectedFile);
      setSelectedFile(null);
      setError(null);
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
        <CardDescription>
          {t("description")}
        </CardDescription>
      </CardHeader>
      <CardContent>
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
              <p className="text-sm text-muted-foreground">
                {t("dropzone")}
              </p>
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

        {error && (
          <p className="mt-2 text-sm text-red-500">{error}</p>
        )}

        {selectedFile && (
          <Button
            className="mt-4 w-full"
            onClick={handleUpload}
            disabled={isUploading}
          >
            {isUploading ? t("uploading") : t("upload")}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
