"use client";

import { useEffect, useRef } from "react";
import { MessageSquare } from "lucide-react";
import { useTranslations } from "next-intl";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ChatMessageBubble } from "./chat-message";
import { Skeleton } from "@/components/ui/skeleton";
import type { ChatMessage } from "@/types/api";

interface ChatMessageListProps {
  messages: ChatMessage[];
  isLoading: boolean;
}

function EmptyState() {
  const t = useTranslations("chat.messages");
  return (
    <div className="flex flex-col items-center justify-center h-full text-center px-4">
      <div className="flex h-16 w-16 items-center justify-center rounded-full bg-primary/10 mb-4">
        <MessageSquare className="h-8 w-8 text-primary" />
      </div>
      <h3 className="text-lg font-semibold">{t("emptyTitle")}</h3>
      <p className="text-muted-foreground mt-2 max-w-sm">
        {t("emptyDescription")}
      </p>
    </div>
  );
}

function LoadingIndicator() {
  const t = useTranslations("chat.messages");
  return (
    <div className="flex gap-3 px-4 py-3" aria-label={t("loading")}>
      <Skeleton className="h-8 w-8 rounded-full shrink-0" />
      <div className="space-y-2 flex-1 max-w-[60%]">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-3/4" />
      </div>
    </div>
  );
}

export function ChatMessageList({ messages, isLoading }: ChatMessageListProps) {
  const t = useTranslations("chat.messages");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  if (!messages.length && !isLoading) {
    return <EmptyState />;
  }

  return (
    <ScrollArea className="flex-1">
      <div className="py-4" role="log" aria-live="polite" aria-label={t("ariaLabel")}>
        {messages.map((message, index) => (
          <ChatMessageBubble key={`${message.role}-${index}-${message.timestamp}`} message={message} />
        ))}
        {isLoading && <LoadingIndicator />}
        <div ref={bottomRef} />
      </div>
    </ScrollArea>
  );
}
