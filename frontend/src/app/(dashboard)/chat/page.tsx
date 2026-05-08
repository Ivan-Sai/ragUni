"use client";

import { useSession } from "next-auth/react";
import { redirect } from "next/navigation";
import { useChat } from "@/hooks/use-chat";
import { ChatMessageList } from "@/components/chat/chat-message-list";
import { ChatInput } from "@/components/chat/chat-input";
import { PersonalizationBanner } from "@/components/chat/personalization-banner";
import { Skeleton } from "@/components/ui/skeleton";

export default function ChatPage() {
  const { data: session, status } = useSession();

  if (status === "unauthenticated") {
    redirect("/login");
  }

  const token = session?.accessToken || "";

  const { messages, isLoading, error, sessionId, sendMessage, clearMessages } = useChat({
    token,
  });

  if (status === "loading") {
    return (
      <div className="flex flex-col h-[calc(100vh-4rem)] -m-6 items-center justify-center gap-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-4 w-64" />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] -m-6">
      <PersonalizationBanner />
      {/* min-h-0 forces the scroll area to shrink instead of pushing
       * the input out of the viewport when sources expand. */}
      <div className="flex-1 min-h-0 flex flex-col">
        <ChatMessageList messages={messages} isLoading={isLoading} sessionId={sessionId} />
      </div>

      {error && (
        <div className="px-4 py-2 text-sm text-destructive bg-destructive/10 border-t shrink-0" role="alert">
          {error}
        </div>
      )}

      {/* Pinned to the bottom of the chat shell — survives any amount
       * of message-list scrolling. */}
      <div className="shrink-0 border-t bg-background sticky bottom-0">
        <ChatInput onSend={sendMessage} isLoading={isLoading} />
      </div>
    </div>
  );
}
