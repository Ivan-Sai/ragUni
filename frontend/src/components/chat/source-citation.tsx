"use client";

import * as React from "react";
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
  /** Assistant answer text — used to count how often each [N] is cited
   * so the most-mentioned source bubbles to the top of the list. */
  answerText?: string;
}

interface IndexedSource extends ChatSource {
  /** Original 1-based index in the LLM context — drives [N] anchor ids. */
  citationIndex: number;
}

interface GroupedSource {
  source_file: string;
  file_type: string;
  document_id?: string;
  topScore: number;
  chunks: IndexedSource[];
  /** Smallest citation index across the group's chunks — used to label the
   * card header with the lowest-numbered citation pointing at this file. */
  primaryIndex: number;
  /** Total number of [N] mentions in the assistant's answer that point
   * at any chunk in this group. Drives the outer sort so heavily-cited
   * documents appear first regardless of vector ranking. */
  mentions: number;
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
 * cards for the same PDF. Each chunk keeps its 1-based citation index
 * (matching the [N] markers the LLM emitted) so anchor links survive
 * the regrouping.
 */
function countCitations(answer: string): Map<number, number> {
  const counts = new Map<number, number>();
  if (!answer) return counts;
  const re = /\[(\d+)\]/g;
  let match: RegExpExecArray | null;
  while ((match = re.exec(answer)) !== null) {
    const n = Number(match[1]);
    if (!Number.isInteger(n) || n < 1) continue;
    counts.set(n, (counts.get(n) ?? 0) + 1);
  }
  return counts;
}

function groupSources(
  sources: ChatSource[],
  answerText?: string,
): GroupedSource[] {
  const indexed: IndexedSource[] = sources.map((s, i) => ({
    ...s,
    citationIndex: i + 1,
  }));
  const citationCounts = countCitations(answerText ?? "");

  const map = new Map<string, GroupedSource>();
  for (const s of indexed) {
    const existing = map.get(s.source_file);
    const score = s.score ?? 0;
    const mentions = citationCounts.get(s.citationIndex) ?? 0;
    if (existing) {
      existing.chunks.push(s);
      existing.topScore = Math.max(existing.topScore, score);
      existing.primaryIndex = Math.min(existing.primaryIndex, s.citationIndex);
      existing.mentions += mentions;
      if (!existing.document_id && s.document_id) {
        existing.document_id = s.document_id;
      }
    } else {
      map.set(s.source_file, {
        source_file: s.source_file,
        file_type: s.file_type,
        document_id: s.document_id,
        topScore: score,
        primaryIndex: s.citationIndex,
        mentions,
        chunks: [s],
      });
    }
  }
  // Each group's chunks list in original citation order.
  for (const group of map.values()) {
    group.chunks.sort((a, b) => a.citationIndex - b.citationIndex);
  }
  // Outer sort: most-cited group first. When citations are tied (or
  // absent — e.g. answer didn't use the [N] format) fall back to the
  // primary citation index so we still mirror the LLM's ordering.
  return Array.from(map.values()).sort((a, b) => {
    if (b.mentions !== a.mentions) return b.mentions - a.mentions;
    return a.primaryIndex - b.primaryIndex;
  });
}

function SourceGroup({
  group,
  onOpen,
}: {
  group: GroupedSource;
  onOpen: (documentId: string, highlight: string) => void;
}) {
  const t = useTranslations("chat.sources");
  // All groups start collapsed; the user expands the one they care
  // about either by clicking it or by clicking [N] in the answer.
  const [open, setOpen] = useState(false);

  // Listen for hash-driven anchor jumps so a click on [N] in the answer
  // expands the right card before the browser scrolls to it.
  React.useEffect(() => {
    function handleAnchor(event: Event) {
      const detail = (event as CustomEvent<{ index: number }>).detail;
      if (!detail) return;
      if (group.chunks.some((c) => c.citationIndex === detail.index)) {
        setOpen(true);
      }
    }
    window.addEventListener("citation-jump", handleAnchor);
    return () => window.removeEventListener("citation-jump", handleAnchor);
  }, [group.chunks]);

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

  // Build the label that appears in the small badge: either a single
  // [N] or a range like [2-5] when several citations share this file.
  const indexLabel =
    group.chunks.length === 1
      ? `${group.chunks[0].citationIndex}`
      : `${group.chunks[0].citationIndex}-${group.chunks[group.chunks.length - 1].citationIndex}`;

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger className="flex w-full items-center gap-2 rounded-md border bg-muted/50 px-3 py-2 text-xs hover:bg-muted transition-colors scroll-mt-20">
        <span className="inline-flex h-5 min-w-[1.25rem] shrink-0 items-center justify-center rounded bg-primary/10 px-1 text-[10px] font-semibold text-primary">
          {indexLabel}
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
                id={`src-${chunk.citationIndex}`}
                className="rounded-md border bg-muted/30 px-3 py-2 scroll-mt-20 target:bg-primary/5 target:ring-1 target:ring-primary/40"
              >
                <div className="mb-1 flex items-center gap-1.5">
                  <span className="inline-flex h-4 min-w-[1rem] items-center justify-center rounded bg-primary/15 px-1 text-[10px] font-semibold text-primary">
                    {chunk.citationIndex}
                  </span>
                </div>
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

export function SourceCitation({ sources, answerText }: SourceCitationProps) {
  const t = useTranslations("chat.sources");
  const allGroups = useMemo(
    () => groupSources(sources, answerText),
    [sources, answerText],
  );

  // Split into "actually cited" and "retrieved but not cited". When the
  // LLM didn't use the [N] format at all we fall back to showing every
  // group so the user is never left wondering where the answer came
  // from.
  const { cited, uncited } = useMemo(() => {
    const c = allGroups.filter((g) => g.mentions > 0);
    const u = allGroups.filter((g) => g.mentions === 0);
    if (c.length === 0) return { cited: u, uncited: [] as GroupedSource[] };
    return { cited: c, uncited: u };
  }, [allGroups]);

  const [outerOpen, setOuterOpen] = useState(false);
  const [showUncited, setShowUncited] = useState(false);
  const [activeDocId, setActiveDocId] = useState<string | null>(null);
  const [activeHighlight, setActiveHighlight] = useState<string | null>(null);

  // A click on [N] in the answer auto-opens the outer toggle so the
  // target card actually exists in the layout when we scroll to it.
  React.useEffect(() => {
    function handleAnchor() {
      setOuterOpen(true);
    }
    window.addEventListener("citation-jump", handleAnchor);
    return () => window.removeEventListener("citation-jump", handleAnchor);
  }, []);

  if (!sources.length) return null;

  function handleOpen(documentId: string, highlight: string) {
    setActiveDocId(documentId);
    setActiveHighlight(highlight);
  }

  return (
    <div className="mt-3">
      <Collapsible open={outerOpen} onOpenChange={setOuterOpen}>
        <CollapsibleTrigger className="flex w-full items-center gap-2 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors">
          <span>{t("title", { count: cited.length })}</span>
          <ChevronDown
            className={cn(
              "h-3.5 w-3.5 transition-transform",
              outerOpen && "rotate-180",
            )}
          />
        </CollapsibleTrigger>
        <CollapsibleContent className="mt-2 space-y-1.5">
          {cited.map((group) => (
            <SourceGroup
              key={group.source_file}
              group={group}
              onOpen={handleOpen}
            />
          ))}

          {uncited.length > 0 && (
            <>
              {showUncited ? (
                <>
                  <p className="pt-2 text-[10px] font-medium uppercase tracking-wide text-muted-foreground/60">
                    {t("uncitedHeader")}
                  </p>
                  {uncited.map((group) => (
                    <SourceGroup
                      key={group.source_file}
                      group={group}
                      onOpen={handleOpen}
                    />
                  ))}
                </>
              ) : (
                <button
                  type="button"
                  className="text-[11px] text-muted-foreground hover:text-foreground transition-colors underline-offset-2 hover:underline"
                  onClick={() => setShowUncited(true)}
                >
                  {t("showUncited", { count: uncited.length })}
                </button>
              )}
            </>
          )}
        </CollapsibleContent>
      </Collapsible>

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
