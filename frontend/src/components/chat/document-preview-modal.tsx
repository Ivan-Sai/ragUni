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
      <DialogContent
        className="!max-w-[min(95vw,72rem)] sm:!max-w-[min(90vw,72rem)] max-h-[85vh] flex flex-col gap-3"
      >
        <DialogHeader className="space-y-1">
          <DialogTitle className="flex items-center gap-2 pr-8">
            <FileIcon type={doc?.file_type ?? "txt"} className="h-5 w-5" />
            <span className="truncate">{doc?.filename ?? t("title")}</span>
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

        {/*
          Plain overflow-y-auto instead of Radix ScrollArea: the latter
          needs an explicit height to know what to scroll, and inside a
          flex column the height it computes via flex-1 + min-h-0 ends
          up unconstrained on some browsers — content then overflows
          past the dialog. A native scroll container with min-h-0 just
          works.
        */}
        <div className="flex-1 min-h-0 overflow-y-auto rounded border bg-muted/30 px-4 py-3">
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
        </div>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Find the highlight inside the document body using a robust prefix
 * match. The chunk preview was truncated to ~350 chars at a sentence
 * boundary and ends in "…", so we strip trailing punctuation, take a
 * stable prefix (first 60 chars after collapsing whitespace), and
 * search case-insensitively. If the prefix isn't found we render the
 * body unchanged — better than highlighting the wrong span.
 */
function findHighlightRange(
  text: string,
  highlight: string,
): { start: number; end: number } | null {
  const cleaned = highlight.replace(/[…\.\s]+$/g, "").trim();
  if (cleaned.length < 8) return null;

  const probeLen = Math.min(60, cleaned.length);
  const probe = cleaned.slice(0, probeLen).toLowerCase();
  const haystack = text.toLowerCase();

  // Try a direct match first.
  let start = haystack.indexOf(probe);
  if (start === -1) {
    // Collapse all whitespace to single spaces in both strings and try
    // again — chunking sometimes normalises whitespace differently
    // from the original document body.
    const normalisedHaystack = haystack.replace(/\s+/g, " ");
    const normalisedProbe = probe.replace(/\s+/g, " ");
    const normalisedStart = normalisedHaystack.indexOf(normalisedProbe);
    if (normalisedStart === -1) return null;
    // Translate the index back into the original (non-normalised) text.
    let consumed = 0;
    for (let i = 0; i < text.length; i++) {
      if (consumed === normalisedStart) {
        start = i;
        break;
      }
      const ch = text[i];
      if (/\s/.test(ch)) {
        if (i + 1 < text.length && /\s/.test(text[i + 1])) continue;
        consumed += 1;
      } else {
        consumed += 1;
      }
    }
    if (start === -1) return null;
  }

  // Highlight spans the full chunk preview length. Chunks legitimately
  // straddle paragraph breaks ("--- Page N ---" markers, table rows,
  // section headers), so clamping at the next "\n\n" leaves visible
  // gaps and was the source of the patchy highlight in the modal.
  const end = Math.min(start + cleaned.length, text.length);
  return { start, end };
}

function DocumentBody({
  text,
  highlight,
}: {
  text: string;
  highlight: string | null;
}) {
  const range = highlight ? findHighlightRange(text, highlight) : null;

  if (!range) {
    return (
      <div className="whitespace-pre-wrap break-words text-sm leading-relaxed">
        {text}
      </div>
    );
  }

  const before = text.slice(0, range.start);
  const middle = text.slice(range.start, range.end);
  const after = text.slice(range.end);

  return (
    <div className="whitespace-pre-wrap break-words text-sm leading-relaxed">
      {before}
      <mark
        data-source-highlight
        className="rounded bg-yellow-200 px-1 py-0.5 dark:bg-yellow-900/60 dark:text-yellow-50"
      >
        {middle}
      </mark>
      {after}
    </div>
  );
}
