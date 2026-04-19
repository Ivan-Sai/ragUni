"use client";

import { useState, useEffect } from "react";
import { useSession } from "next-auth/react";
import { FileText } from "lucide-react";
import { useTranslations } from "next-intl";
import { documentsApi } from "@/lib/api";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";

interface DocumentPreviewProps {
  documentId: string | null;
  filename: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function DocumentPreview({
  documentId,
  filename,
  open,
  onOpenChange,
}: DocumentPreviewProps) {
  const { data: session } = useSession();
  const t = useTranslations("admin.documents");
  const token = session?.accessToken || "";
  const [text, setText] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !documentId || !token) {
      setText(null);
      setError(null);
      return;
    }

    setLoading(true);
    setError(null);
    documentsApi
      .getPreview(documentId, token)
      .then((result) => setText(result.text))
      .catch((err) => {
        const message =
          err instanceof Error ? err.message : t("previewLoadError");
        setError(message);
      })
      .finally(() => setLoading(false));
  }, [open, documentId, token, t]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[80vh]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5" />
            {filename}
          </DialogTitle>
          <DialogDescription>{t("previewDescription")}</DialogDescription>
        </DialogHeader>
        <ScrollArea className="h-[60vh]">
          {loading && (
            <div className="space-y-2 p-4">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-4 w-5/6" />
            </div>
          )}
          {error && (
            <p className="p-4 text-sm text-destructive">{error}</p>
          )}
          {text && (
            <pre className="whitespace-pre-wrap text-sm p-4 font-sans leading-relaxed">
              {text}
            </pre>
          )}
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}
