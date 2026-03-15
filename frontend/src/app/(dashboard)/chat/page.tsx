"use client";

import { useSession } from "next-auth/react";
import { redirect } from "next/navigation";
import { useChat } from "@/hooks/use-chat";
import { ChatMessageList } from "@/components/chat/chat-message-list";
import { ChatInput } from "@/components/chat/chat-input";
import { Skeleton } from "@/components/ui/skeleton";

export default function ChatPage() {
  const { data: session, status } = useSession();

  if (status === "unauthenticated") {
    redirect("/login");
  }

  const token = session?.accessToken || "";

  const { messages, isLoading, error, sendMessage, clearMessages } = useChat({
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
      <ChatMessageList messages={messages} isLoading={isLoading} />

      {error && (
        <div className="px-4 py-2 text-sm text-destructive bg-destructive/10 border-t" role="alert">
          {error}
        </div>
      )}

      <ChatInput onSend={sendMessage} isLoading={isLoading} />
    </div>
  );
}
