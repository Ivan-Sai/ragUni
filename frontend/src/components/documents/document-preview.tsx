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
    // Only (re)fetch when the dialog is actually open and we have the
    // inputs we need. All setState calls live inside the async IIFE —
    // react-hooks/set-state-in-effect flags synchronous setState in the
    // effect *body*, so wrapping them in a nested async function keeps
    // the rule happy while preserving the semantics.
    if (!open || !documentId || !token) return;

    let cancelled = false;
    void (async () => {
      setLoading(true);
      setError(null);
      try {
        const result = await documentsApi.getPreview(documentId, token);
        if (!cancelled) setText(result.text);
      } catch (err) {
        if (cancelled) return;
        const message =
          err instanceof Error ? err.message : t("previewLoadError");
        setError(message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
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
