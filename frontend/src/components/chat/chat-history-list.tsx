"use client";

import Link from "next/link";
import { MessageSquare, Trash2, Plus } from "lucide-react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import {
  SidebarGroup,
  SidebarGroupLabel,
  SidebarGroupContent,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
} from "@/components/ui/sidebar";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { ChatSessionPreview } from "@/types/api";

interface ChatHistoryListProps {
  sessions: ChatSessionPreview[];
  isLoading: boolean;
  activeSessionId: string | null;
  onDelete: (sessionId: string) => void;
  onNewChat: () => void;
}

function formatDate(dateStr: string, t: (key: string) => string): string {
  const date = new Date(dateStr);
  if (isNaN(date.getTime())) return "";

  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const days = Math.floor(diff / (1000 * 60 * 60 * 24));

  if (days === 0) return t("today");
  if (days === 1) return t("yesterday");
  if (days < 7) return `${days} ${t("daysAgo")}`;
  return date.toLocaleDateString("uk-UA", { day: "numeric", month: "short" });
}

export function ChatHistoryList({
  sessions,
  isLoading,
  activeSessionId,
  onDelete,
  onNewChat,
}: ChatHistoryListProps) {
  const t = useTranslations("chat.history");
  return (
    <SidebarGroup>
      <SidebarGroupLabel className="flex items-center justify-between">
        <span>{t("title")}</span>
        <Button
          variant="ghost"
          size="icon-xs"
          onClick={onNewChat}
          title={t("newChat")}
        >
          <Plus className="h-3.5 w-3.5" />
        </Button>
      </SidebarGroupLabel>
      <SidebarGroupContent>
        {isLoading ? (
          <div className="space-y-2 px-2">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-3/4" />
          </div>
        ) : sessions.length === 0 ? (
          <p className="px-3 py-2 text-xs text-muted-foreground">
            {t("empty")}
          </p>
        ) : (
          <SidebarMenu>
            {sessions.map((session) => (
              <SidebarMenuItem key={session.session_id} className="group/item">
                <SidebarMenuButton
                  render={<Link href={`/chat/${session.session_id}`} />}
                  className={cn(
                    activeSessionId === session.session_id && "bg-muted"
                  )}
                >
                  <MessageSquare className="h-4 w-4 shrink-0" />
                  <div className="flex flex-col min-w-0 flex-1">
                    <span className="truncate text-xs">
                      {session.title || t("untitled")}
                    </span>
                    <span className="text-[10px] text-muted-foreground">
                      {formatDate(session.updated_at, t)}
                    </span>
                  </div>
                </SidebarMenuButton>
                <Button
                  variant="ghost"
                  size="icon-xs"
                  className="absolute right-1 top-1/2 -translate-y-1/2 opacity-0 group-hover/item:opacity-100 transition-opacity"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    onDelete(session.session_id);
                  }}
                >
                  <Trash2 className="h-3 w-3 text-muted-foreground" />
                </Button>
              </SidebarMenuItem>
            ))}
          </SidebarMenu>
        )}
      </SidebarGroupContent>
    </SidebarGroup>
  );
}
