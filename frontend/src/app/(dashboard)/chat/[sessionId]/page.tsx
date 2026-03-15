"use client";

import { useParams } from "next/navigation";
import { useSession } from "next-auth/react";
import { useChat } from "@/hooks/use-chat";
import { ChatMessageList } from "@/components/chat/chat-message-list";
import { ChatInput } from "@/components/chat/chat-input";

export default function ChatSessionPage() {
  const params = useParams<{ sessionId: string }>();
  const { data: session } = useSession();
  const token = session?.accessToken || "";

  const { messages, isLoading, error, sendMessage } = useChat({
    token,
    sessionId: params.sessionId,
  });

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] -m-6">
      <ChatMessageList messages={messages} isLoading={isLoading} />

      {error && (
        <div className="px-4 py-2 text-sm text-destructive bg-destructive/10 border-t">
          {error}
        </div>
      )}

      <ChatInput onSend={sendMessage} isLoading={isLoading} />
    </div>
  );
}
