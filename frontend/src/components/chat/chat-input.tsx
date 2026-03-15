"use client";

import { useState, useRef, type KeyboardEvent } from "react";
import { Send } from "lucide-react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

interface ChatInputProps {
  onSend: (message: string) => void;
  isLoading: boolean;
}

const MAX_LENGTH = 5000;
const WARN_THRESHOLD = 4800;

export function ChatInput({ onSend, isLoading }: ChatInputProps) {
  const t = useTranslations("chat.input");
  const [input, setInput] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function handleSend() {
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;
    onSend(trimmed);
    setInput("");
    textareaRef.current?.focus();
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="flex gap-2 items-end p-4 border-t bg-background">
      <div className="flex-1 relative">
        <Textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={t("placeholder")}
          aria-label={t("ariaLabel")}
          disabled={isLoading}
          maxLength={MAX_LENGTH}
          className="min-h-10 max-h-40 resize-none"
          rows={1}
        />
        {input.length >= WARN_THRESHOLD && (
          <span className="absolute bottom-1 right-2 text-xs text-muted-foreground">
            {input.length}/{MAX_LENGTH}
          </span>
        )}
      </div>
      <Button
        onClick={handleSend}
        disabled={!input.trim() || isLoading}
        size="icon"
        aria-label={t("sendAriaLabel")}
      >
        <Send className="h-4 w-4" />
      </Button>
    </div>
  );
}
