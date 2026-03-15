"use client";

import { useState } from "react";
import { FileText, ChevronDown } from "lucide-react";
import { useTranslations } from "next-intl";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import type { ChatSource } from "@/types/api";

interface SourceCitationProps {
  sources: ChatSource[];
}

function SourceCard({ source }: { source: ChatSource }) {
  const t = useTranslations("chat.sources");
  const [open, setOpen] = useState(false);

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger className="flex w-full items-center gap-2 rounded-md border bg-muted/50 px-3 py-2 text-xs hover:bg-muted transition-colors">
        <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <span className="truncate font-medium">{source.source_file}</span>
        {source.score !== undefined && (
          <span className="ml-auto text-muted-foreground shrink-0">
            {Math.round(source.score * 100)}%
          </span>
        )}
        <ChevronDown
          className={cn(
            "h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform",
            open && "rotate-180"
          )}
        />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="mt-1 rounded-md border bg-muted/30 px-3 py-2">
          <p className="text-xs text-muted-foreground whitespace-pre-wrap">
            {source.text}
          </p>
          <p className="text-[10px] text-muted-foreground/60 mt-1">
            {t("chunk")}{source.chunk_index + 1}
            {source.total_chunks ? t("chunkOf", { total: source.total_chunks }) : ""}
            {source.file_type ? ` · ${source.file_type.toUpperCase()}` : ""}
          </p>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

export function SourceCitation({ sources }: SourceCitationProps) {
  const t = useTranslations("chat.sources");
  if (!sources.length) return null;

  return (
    <div className="mt-3 space-y-1.5">
      <p className="text-xs font-medium text-muted-foreground">
        {t("title", { count: sources.length })}
      </p>
      {sources.map((source) => (
        <SourceCard key={`${source.source_file}-${source.chunk_index}`} source={source} />
      ))}
    </div>
  );
}
