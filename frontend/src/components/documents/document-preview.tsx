"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { FileText, Loader2, Sparkles } from "lucide-react";
import { useTranslations } from "next-intl";
import { documentsApi } from "@/lib/api";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { DocumentPreviewResponse } from "@/types/api";
import { RecordCards } from "@/components/documents/record-cards";

interface DocumentPreviewProps {
  documentId: string | null;
  filename: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

type ViewMode = "structured" | "raw";

export function DocumentPreview({
  documentId,
  filename,
  open,
  onOpenChange,
}: DocumentPreviewProps) {
  const { data: session } = useSession();
  const t = useTranslations("admin.documents");
  const token = session?.accessToken || "";
  const [doc, setDoc] = useState<DocumentPreviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<ViewMode>("structured");

  useEffect(() => {
    if (!open || !documentId || !token) return;
    let cancelled = false;
    void (async () => {
      setLoading(true);
      setError(null);
      try {
        const result = await documentsApi.getPreview(documentId, token);
        if (!cancelled) {
          setDoc(result);
          // Default to structured view whenever the document has it,
          // since that's what RAG actually searches against. Fall back
          // to raw for legacy documents indexed before LLM extraction.
          setView(result.structured_text ? "structured" : "raw");
        }
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : t("previewLoadError"));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, documentId, token, t]);

  const hasStructured = Boolean(doc?.structured_text);
  const showCards =
    view === "structured" && (doc?.structured_records?.length ?? 0) > 0;
  const body =
    view === "structured" && doc?.structured_text
      ? doc.structured_text
      : doc?.text ?? "";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="!max-w-[min(95vw,72rem)] sm:!max-w-[min(90vw,72rem)] max-h-[85vh] flex flex-col gap-3">
        <DialogHeader className="space-y-1">
          <DialogTitle className="flex items-center gap-2 pr-8">
            <FileText className="h-5 w-5" />
            <span className="truncate">{filename}</span>
            {hasStructured && (
              <span className="ml-2 inline-flex items-center gap-1 rounded bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary">
                <Sparkles className="h-3 w-3" />
                {t("llmExtractedBadge", {
                  count: doc?.structured_records_count ?? 0,
                })}
              </span>
            )}
          </DialogTitle>
          <DialogDescription>{t("previewDescription")}</DialogDescription>
        </DialogHeader>

        {hasStructured && (
          <div className="flex gap-1 border-b">
            <ViewTab
              active={view === "structured"}
              onClick={() => setView("structured")}
              label={t("viewStructured")}
            />
            <ViewTab
              active={view === "raw"}
              onClick={() => setView("raw")}
              label={t("viewRaw")}
            />
          </div>
        )}

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
          ) : showCards ? (
            <RecordCards records={doc!.structured_records} />
          ) : (
            <div className="whitespace-pre-wrap break-words text-sm leading-relaxed font-sans">
              {body}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function ViewTab({
  active,
  onClick,
  label,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        "border-b-2 px-3 py-1.5 text-xs font-medium transition-colors " +
        (active
          ? "border-primary text-foreground"
          : "border-transparent text-muted-foreground hover:text-foreground")
      }
    >
      {label}
    </button>
  );
}
