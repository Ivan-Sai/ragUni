"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Trash2, FileText, FileSpreadsheet, File } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import type { DocumentInfo } from "@/types/api";

interface DocumentsTableProps {
  documents: DocumentInfo[];
  isLoading: boolean;
  onDelete: (documentId: string) => Promise<void>;
}

const fileTypeIcons: Record<string, typeof FileText> = {
  pdf: FileText,
  docx: File,
  xlsx: FileSpreadsheet,
};

const fileTypeBadge: Record<string, "default" | "secondary" | "outline"> = {
  pdf: "default",
  docx: "secondary",
  xlsx: "outline",
};

function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString("uk-UA", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function DocumentsTable({
  documents,
  isLoading,
  onDelete,
}: DocumentsTableProps) {
  const t = useTranslations("admin.documents");
  const [deletingId, setDeletingId] = useState<string | null>(null);

  async function handleDelete(documentId: string) {
    setDeletingId(documentId);
    try {
      await onDelete(documentId);
    } finally {
      setDeletingId(null);
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t("file")}</TableHead>
            <TableHead>{t("type")}</TableHead>
            <TableHead>{t("chunks")}</TableHead>
            <TableHead>{t("uploaded")}</TableHead>
            <TableHead className="text-right">{t("actions")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {documents.length === 0 ? (
            <TableRow>
              <TableCell colSpan={5} className="text-center text-muted-foreground">
                {t("empty")}
              </TableCell>
            </TableRow>
          ) : (
            documents.map((doc) => {
              const Icon = fileTypeIcons[doc.file_type] || File;
              return (
                <TableRow key={doc.id}>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Icon className="h-4 w-4 text-muted-foreground" />
                      <span className="font-medium">{doc.filename}</span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant={fileTypeBadge[doc.file_type] || "outline"}>
                      {doc.file_type.toUpperCase()}
                    </Badge>
                  </TableCell>
                  <TableCell>{doc.total_chunks}</TableCell>
                  <TableCell>{formatDate(doc.uploaded_at)}</TableCell>
                  <TableCell className="text-right">
                    <AlertDialog>
                      <AlertDialogTrigger
                        disabled={deletingId === doc.id}
                        render={<Button variant="ghost" size="sm" />}
                      >
                        <Trash2 className="h-4 w-4 text-red-500" />
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>
                            {t("deleteTitle")}
                          </AlertDialogTitle>
                          <AlertDialogDescription>
                            {t("deleteDescription", { filename: doc.filename })}
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>{t("cancel")}</AlertDialogCancel>
                          <AlertDialogAction
                            onClick={() => handleDelete(doc.id)}
                            className="bg-red-600 hover:bg-red-700"
                          >
                            {t("delete")}
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </TableCell>
                </TableRow>
              );
            })
          )}
        </TableBody>
      </Table>
    </div>
  );
}
