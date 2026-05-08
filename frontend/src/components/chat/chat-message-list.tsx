"use client";

import { useEffect, useRef } from "react";
import { MessageSquare } from "lucide-react";
import { useTranslations } from "next-intl";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ChatMessageBubble } from "./chat-message";
import type { ChatMessage } from "@/types/api";

interface ChatMessageListProps {
  messages: ChatMessage[];
  isLoading: boolean;
  sessionId?: string | null;
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
  // Three-dot "typing" animation reuses Tailwind's bounce keyframe
  // staggered by negative animation-delays. Goes alongside an
  // explicit text label so the user understands the request is alive
  // even before the first SSE token lands (which can be several
  // seconds for Atlas Vector Search + first LLM token).
  return (
    <div className="flex gap-3 px-4 py-3" aria-label={t("loading")}>
      <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
        <span className="text-xs font-semibold text-primary">A</span>
      </div>
      <div className="flex-1 space-y-1">
        <p className="text-xs font-medium text-muted-foreground">
          {t("loading")}
        </p>
        <div className="flex items-center gap-1">
          <span className="h-2 w-2 rounded-full bg-primary/60 animate-bounce [animation-delay:-0.3s]" />
          <span className="h-2 w-2 rounded-full bg-primary/60 animate-bounce [animation-delay:-0.15s]" />
          <span className="h-2 w-2 rounded-full bg-primary/60 animate-bounce" />
        </div>
      </div>
    </div>
  );
}

export function ChatMessageList({ messages, isLoading, sessionId }: ChatMessageListProps) {
  const t = useTranslations("chat.messages");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  if (!messages.length && !isLoading) {
    return <EmptyState />;
  }

  // Show the typing dots ONLY before the first token arrives. Once
  // the assistant bubble has content, the streaming text itself is
  // the progress signal — leaving the indicator on would render as
  // a duplicate "loading" widget below an already-complete answer.
  const lastMessage = messages[messages.length - 1];
  const isWaitingForFirstToken =
    isLoading &&
    (!lastMessage ||
      lastMessage.role === "user" ||
      (lastMessage.role === "assistant" && lastMessage.content.length === 0));

  return (
    <ScrollArea className="flex-1 min-h-0">
      <div className="py-4" role="log" aria-live="polite" aria-label={t("ariaLabel")}>
        {messages.map((message, index) => (
          <ChatMessageBubble key={`${message.role}-${index}-${message.timestamp}`} message={message} messageIndex={index} sessionId={sessionId} />
        ))}
        {isWaitingForFirstToken && <LoadingIndicator />}
        <div ref={bottomRef} />
      </div>
    </ScrollArea>
  );
}
