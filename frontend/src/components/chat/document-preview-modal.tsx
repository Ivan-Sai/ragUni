"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useSession } from "next-auth/react";
import { FileText, FileSpreadsheet, FileType, Loader2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { documentsApi } from "@/lib/api";
import type { DocumentPreviewResponse } from "@/types/api";

interface DocumentPreviewModalProps {
  documentId: string | null;
  highlight?: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function FileIcon({
  type,
  className,
}: {
  type: string;
  className?: string;
}) {
  switch (type.toLowerCase()) {
    case "pdf":
      return <FileType className={className} />;
    case "xlsx":
      return <FileSpreadsheet className={className} />;
    case "docx":
    default:
      return <FileText className={className} />;
  }
}

/**
 * Reads the extracted text of a document and renders it inside a modal.
 * The matching ``highlight`` snippet — usually the chunk preview from
 * the source card the user clicked — is auto-scrolled into view and
 * visually marked, so the reader lands directly on the cited fragment.
 */
export function DocumentPreviewModal({
  documentId,
  highlight,
  open,
  onOpenChange,
}: DocumentPreviewModalProps) {
  const t = useTranslations("chat.preview");
  const { data: session } = useSession();
  const [doc, setDoc] = useState<DocumentPreviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !documentId || !session?.accessToken) return;
    let cancelled = false;
    void (async () => {
      setLoading(true);
      setError(null);
      try {
        const result = await documentsApi.getPreview(
          documentId,
          session.accessToken,
        );
        if (!cancelled) setDoc(result);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : t("loadError"));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, documentId, session?.accessToken, t]);

  // Auto-scroll the highlighted snippet into view once the modal renders.
  useEffect(() => {
    if (!open || !highlight || !doc) return;
    const id = setTimeout(() => {
      const target = document.querySelector("[data-source-highlight]");
      if (target) {
        target.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }, 100);
    return () => clearTimeout(id);
  }, [open, highlight, doc]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileIcon type={doc?.file_type ?? "txt"} className="h-5 w-5" />
            {doc?.filename ?? t("title")}
          </DialogTitle>
          <DialogDescription>
            {doc
              ? t("info", {
                  type: doc.file_type.toUpperCase(),
                  chunks: doc.total_chunks,
                })
              : t("loading")}
          </DialogDescription>
        </DialogHeader>

        <ScrollArea className="flex-1 rounded border bg-muted/30 px-3 py-2">
          {loading ? (
            <div className="flex items-center justify-center py-12 text-muted-foreground">
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              {t("loading")}
            </div>
          ) : error ? (
            <p className="py-12 text-center text-sm text-destructive">
              {error}
            </p>
          ) : doc ? (
            <DocumentBody text={doc.text} highlight={highlight ?? null} />
          ) : null}
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}

function DocumentBody({
  text,
  highlight,
}: {
  text: string;
  highlight: string | null;
}) {
  if (!highlight) {
    return (
      <pre className="whitespace-pre-wrap break-words text-sm font-sans">
        {text}
      </pre>
    );
  }

  // Strip the trailing ellipsis the source preview adds and look for the
  // longest stable prefix in the document body.
  const trimmed = highlight.replace(/[…\.]+$/g, "").trim();
  const probe = trimmed.length > 80 ? trimmed.slice(0, 80) : trimmed;
  const idx = probe ? text.toLowerCase().indexOf(probe.toLowerCase()) : -1;

  if (idx === -1) {
    return (
      <pre className="whitespace-pre-wrap break-words text-sm font-sans">
        {text}
      </pre>
    );
  }

  const matchEnd = idx + (trimmed.length || probe.length);
  const before = text.slice(0, idx);
  const middle = text.slice(idx, matchEnd);
  const after = text.slice(matchEnd);

  return (
    <pre className="whitespace-pre-wrap break-words text-sm font-sans">
      {before}
      <mark
        data-source-highlight
        className="rounded bg-yellow-200 px-1 dark:bg-yellow-900/60"
      >
        {middle}
      </mark>
      {after}
    </pre>
  );
}
