"use client";

import { useParams } from "next/navigation";
import { useSession } from "next-auth/react";
import { useChat } from "@/hooks/use-chat";
import { ChatMessageList } from "@/components/chat/chat-message-list";
import { ChatInput } from "@/components/chat/chat-input";
import { PersonalizationBanner } from "@/components/chat/personalization-banner";

export default function ChatSessionPage() {
  const params = useParams<{ sessionId: string }>();
  const { data: session } = useSession();
  const token = session?.accessToken || "";

  const { messages, isLoading, error, sessionId, sendMessage } = useChat({
    token,
    sessionId: params.sessionId,
  });

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] -m-6">
      <PersonalizationBanner />
      <div className="flex-1 min-h-0 flex flex-col">
        <ChatMessageList messages={messages} isLoading={isLoading} sessionId={sessionId} />
      </div>

      {error && (
        <div className="px-4 py-2 text-sm text-destructive bg-destructive/10 border-t shrink-0">
          {error}
        </div>
      )}

      <div className="shrink-0 border-t bg-background sticky bottom-0">
        <ChatInput onSend={sendMessage} isLoading={isLoading} />
      </div>
    </div>
  );
}
