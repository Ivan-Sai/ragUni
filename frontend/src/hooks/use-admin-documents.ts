"use client";

import { useState, useCallback, useEffect } from "react";
import { useTranslations } from "next-intl";
import { toast } from "sonner";
import { documentsApi } from "@/lib/api";
import type { DocumentInfo, DocumentUploadOptions } from "@/types/api";

interface UseAdminDocumentsOptions {
  token: string;
}

interface UseAdminDocumentsReturn {
  documents: DocumentInfo[];
  total: number;
  isLoading: boolean;
  isUploading: boolean;
  error: string | null;
  uploadDocument: (
    file: File,
    options: DocumentUploadOptions,
  ) => Promise<void>;
  deleteDocument: (documentId: string) => Promise<void>;
  refresh: () => Promise<void>;
}

export function useAdminDocuments({
  token,
}: UseAdminDocumentsOptions): UseAdminDocumentsReturn {
  const t = useTranslations("admin.upload");
  const tCommon = useTranslations("common");
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchDocuments = useCallback(async () => {
    if (!token) return;

    setIsLoading(true);
    setError(null);

    try {
      const data = await documentsApi.list(token);
      setDocuments(data.documents);
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : tCommon("unknownError"));
    } finally {
      setIsLoading(false);
    }
  }, [token, tCommon]);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  const uploadDocument = useCallback(
    async (file: File, options: DocumentUploadOptions) => {
      setIsUploading(true);
      setError(null);

      try {
        const result = await documentsApi.upload(file, token, options);
        setDocuments((prev) => [
          {
            id: result.id,
            filename: result.filename,
            file_type: result.file_type,
            access_level: result.access_level,
            faculty_id: result.faculty_id,
            target_group_ids: result.target_group_ids,
            target_years: result.target_years,
            target_level: result.target_level,
            uploaded_at: result.uploaded_at,
            total_chunks: result.total_chunks,
          },
          ...prev,
        ]);
        setTotal((prev) => prev + 1);
        toast.success(t("success"));
      } catch (err) {
        setError(err instanceof Error ? err.message : t("errorDescription"));
        // Surface the backend's reason on the toast (server already
        // localises 4xx detail messages to the user's language).
        toast.error(
          err instanceof Error && err.message
            ? err.message
            : t("errorDescription"),
        );
        throw err;
      } finally {
        setIsUploading(false);
      }
    },
    [token, t]
  );

  const deleteDocument = useCallback(
    async (documentId: string) => {
      await documentsApi.delete(documentId, token);
      setDocuments((prev) => prev.filter((d) => d.id !== documentId));
      setTotal((prev) => prev - 1);
      toast.success(t("success"));
    },
    [token, t]
  );

  return {
    documents,
    total,
    isLoading,
    isUploading,
    error,
    uploadDocument,
    deleteDocument,
    refresh: fetchDocuments,
  };
}
