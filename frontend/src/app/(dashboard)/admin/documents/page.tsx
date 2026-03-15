"use client";

import { useSession } from "next-auth/react";
import { redirect } from "next/navigation";
import { useTranslations } from "next-intl";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DocumentsTable } from "@/components/admin/documents-table";
import { DocumentUpload } from "@/components/admin/document-upload";
import { useAdminDocuments } from "@/hooks/use-admin-documents";

export default function AdminDocumentsPage() {
  const { data: session } = useSession();

  if (session?.user?.role !== "admin") {
    redirect("/chat");
  }

  const t = useTranslations("admin.documents");
  const token = session?.accessToken || "";

  const {
    documents,
    total,
    isLoading,
    isUploading,
    error,
    uploadDocument,
    deleteDocument,
    refresh,
  } = useAdminDocuments({ token });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            {t("title")}
          </h1>
          <p className="text-muted-foreground">
            {t("totalCount", { count: total })}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={refresh}>
          <RefreshCw className="mr-2 h-4 w-4" />
          {t("refresh")}
        </Button>
      </div>

      {error && (
        <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      <DocumentUpload onUpload={uploadDocument} isUploading={isUploading} />

      <DocumentsTable
        documents={documents}
        isLoading={isLoading}
        onDelete={deleteDocument}
      />
    </div>
  );
}
