"use client";

import { useMemo, useState } from "react";
import {
  ChevronDown,
  Copy,
  ExternalLink,
  FileSpreadsheet,
  FileText,
  FileType,
  AlertCircle,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { toast } from "sonner";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ChatSource } from "@/types/api";
import { DocumentPreviewModal } from "./document-preview-modal";

interface SourceCitationProps {
  sources: ChatSource[];
}

interface GroupedSource {
  source_file: string;
  file_type: string;
  document_id?: string;
  topScore: number;
  chunks: ChatSource[];
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
    case "txt":
    default:
      return <FileText className={className} />;
  }
}

/**
 * Group raw chunks by source_file so the user sees one card per
 * document with N expanded fragments inside, instead of N separate
 * cards for the same PDF.
 */
function groupSources(sources: ChatSource[]): GroupedSource[] {
  const map = new Map<string, GroupedSource>();
  for (const s of sources) {
    const existing = map.get(s.source_file);
    const score = s.score ?? 0;
    if (existing) {
      existing.chunks.push(s);
      existing.topScore = Math.max(existing.topScore, score);
      if (!existing.document_id && s.document_id) {
        existing.document_id = s.document_id;
      }
    } else {
      map.set(s.source_file, {
        source_file: s.source_file,
        file_type: s.file_type,
        document_id: s.document_id,
        topScore: score,
        chunks: [s],
      });
    }
  }
  // Sort each group's chunks by score (highest first), then sort the
  // groups by their best chunk's score.
  for (const group of map.values()) {
    group.chunks.sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
  }
  return Array.from(map.values()).sort((a, b) => b.topScore - a.topScore);
}

function SourceGroup({
  group,
  index,
  onOpen,
}: {
  group: GroupedSource;
  index: number;
  onOpen: (documentId: string, highlight: string) => void;
}) {
  const t = useTranslations("chat.sources");
  const [open, setOpen] = useState(index === 0); // first group expanded

  async function copyCitation(chunk: ChatSource) {
    const parts = [chunk.source_file];
    if (chunk.page) parts.push(t("pageRef", { page: chunk.page }));
    parts.push(t("chunkRef", { chunk: chunk.chunk_index + 1 }));
    const citation = parts.join(", ");
    try {
      await navigator.clipboard.writeText(citation);
      toast.success(t("copied"));
    } catch {
      toast.error(t("copyFailed"));
    }
  }

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger
        id={`src-${index + 1}`}
        className="flex w-full items-center gap-2 rounded-md border bg-muted/50 px-3 py-2 text-xs hover:bg-muted transition-colors scroll-mt-20"
      >
        <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded bg-primary/10 text-[10px] font-semibold text-primary">
          {index + 1}
        </span>
        <FileIcon
          type={group.file_type}
          className="h-3.5 w-3.5 shrink-0 text-muted-foreground"
        />
        <span className="truncate font-medium text-left flex-1">
          {group.source_file}
        </span>
        {group.chunks.length > 1 && (
          <span className="text-muted-foreground shrink-0">
            {t("fragmentCount", { count: group.chunks.length })}
          </span>
        )}
        {group.topScore > 0 && (
          <span className="text-muted-foreground shrink-0">
            {Math.round(group.topScore * 100)}%
          </span>
        )}
        <ChevronDown
          className={cn(
            "h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform",
            open && "rotate-180",
          )}
        />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="mt-1 space-y-2">
          {group.chunks.map((chunk, i) => {
            const canOpen = Boolean(group.document_id);
            return (
              <div
                key={`${chunk.source_file}-${chunk.chunk_index}-${i}`}
                className="rounded-md border bg-muted/30 px-3 py-2"
              >
                <p className="text-xs text-muted-foreground whitespace-pre-wrap break-words">
                  {chunk.text}
                </p>
                <div className="mt-1.5 flex items-center justify-between gap-2">
                  <p className="text-[10px] text-muted-foreground/70">
                    {chunk.page
                      ? t("pageAndChunk", {
                          page: chunk.page,
                          chunk: chunk.chunk_index + 1,
                        })
                      : t("chunkOnly", { chunk: chunk.chunk_index + 1 })}
                    {chunk.total_chunks
                      ? t("ofTotal", { total: chunk.total_chunks })
                      : ""}
                  </p>
                  <div className="flex gap-0.5">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6"
                      title={t("copyCitation")}
                      onClick={() => copyCitation(chunk)}
                    >
                      <Copy className="h-3 w-3" />
                    </Button>
                    {canOpen && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6"
                        title={t("openDocument")}
                        onClick={() =>
                          onOpen(group.document_id!, chunk.text)
                        }
                      >
                        <ExternalLink className="h-3 w-3" />
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

export function SourceCitation({ sources }: SourceCitationProps) {
  const t = useTranslations("chat.sources");
  const groups = useMemo(() => groupSources(sources), [sources]);
  const [activeDocId, setActiveDocId] = useState<string | null>(null);
  const [activeHighlight, setActiveHighlight] = useState<string | null>(null);

  if (!sources.length) return null;

  function handleOpen(documentId: string, highlight: string) {
    setActiveDocId(documentId);
    setActiveHighlight(highlight);
  }

  return (
    <div className="mt-3 space-y-1.5">
      <p className="text-xs font-medium text-muted-foreground">
        {t("title", { count: groups.length })}
      </p>
      {groups.map((group, idx) => (
        <SourceGroup
          key={group.source_file}
          group={group}
          index={idx}
          onOpen={handleOpen}
        />
      ))}

      <DocumentPreviewModal
        documentId={activeDocId}
        highlight={activeHighlight}
        open={Boolean(activeDocId)}
        onOpenChange={(open) => {
          if (!open) {
            setActiveDocId(null);
            setActiveHighlight(null);
          }
        }}
      />
    </div>
  );
}

/**
 * Banner shown on assistant messages when the answer was generated
 * without any sources. Either the no-answer guard tripped or — for
 * older sessions — sources were never persisted. Either way, the user
 * deserves a visible "trust this less" signal.
 */
export function NoSourcesWarning() {
  const t = useTranslations("chat.sources");
  return (
    <div className="mt-3 flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-50/50 px-3 py-2 text-xs text-amber-900 dark:bg-amber-900/20 dark:text-amber-200">
      <AlertCircle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
      <span>{t("noSourcesWarning")}</span>
    </div>
  );
}
