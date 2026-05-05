"use client";

import { useState } from "react";
import { useSession } from "next-auth/react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { User, Bot, ThumbsUp, ThumbsDown } from "lucide-react";
import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";
import { NoSourcesWarning, SourceCitation } from "./source-citation";
import { Button } from "@/components/ui/button";
import { chatApi } from "@/lib/api";
import type { ChatMessage, ChatSource } from "@/types/api";

// Allowed HTML elements for markdown rendering (XSS protection)
const ALLOWED_ELEMENTS = [
  "p", "br", "strong", "em", "del", "h1", "h2", "h3", "h4", "h5", "h6",
  "ul", "ol", "li", "blockquote", "code", "pre", "a", "table", "thead",
  "tbody", "tr", "th", "td", "hr", "sup", "sub",
];

/**
 * Replace `[N]` markers in the assistant's answer with markdown links
 * pointing to anchors generated for each source. The link's href uses
 * the format `#src-N`; the SourceCitation component renders matching
 * anchor ids on each numbered group, so a click scrolls the user to
 * the corresponding card. We escape regex meta-characters and skip
 * markers whose number is out of range so a hallucinated `[42]` does
 * not produce a dead link.
 */
function linkifyCitations(content: string, sourceCount: number): string {
  if (!sourceCount) return content;
  return content.replace(/\[(\d+)\]/g, (match, raw: string) => {
    const n = Number(raw);
    if (!Number.isInteger(n) || n < 1 || n > sourceCount) return match;
    return `[\\[${n}\\]](#src-${n})`;
  });
}

interface ChatMessageBubbleProps {
  message: ChatMessage;
  messageIndex?: number;
  sessionId?: string | null;
}

export function ChatMessageBubble({
  message,
  messageIndex,
  sessionId,
}: ChatMessageBubbleProps) {
  const { data: session } = useSession();
  const t = useTranslations("chat.messages");
  const isUser = message.role === "user";
  const sources: ChatSource[] = message.sources ?? [];
  const hasSources = !isUser && sources.length > 0;
  const showNoSourcesWarning =
    !isUser && sources.length === 0 && message.content.trim().length > 0;
  const [feedback, setFeedback] = useState<"thumbs_up" | "thumbs_down" | null>(
    null
  );
  const [feedbackLoading, setFeedbackLoading] = useState(false);

  const canFeedback =
    !isUser &&
    sessionId &&
    messageIndex !== undefined &&
    session?.accessToken;

  async function handleFeedback(type: "thumbs_up" | "thumbs_down") {
    if (!sessionId || messageIndex === undefined || !session?.accessToken)
      return;
    setFeedbackLoading(true);
    try {
      await chatApi.submitFeedback(
        {
          session_id: sessionId,
          message_index: messageIndex,
          feedback_type: type,
        },
        session.accessToken
      );
      setFeedback(type);
    } catch {
      // silently ignore feedback errors
    } finally {
      setFeedbackLoading(false);
    }
  }

  return (
    <div
      className={cn(
        "flex gap-3 px-4 py-3",
        isUser ? "justify-end" : "justify-start"
      )}
    >
      {!isUser && (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10">
          <Bot className="h-4 w-4 text-primary" />
        </div>
      )}

      <div
        className={cn(
          "max-w-[80%] rounded-lg px-4 py-2",
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-muted"
        )}
      >
        <p className="text-xs font-medium mb-1 opacity-70">
          {isUser ? t("you") : t("assistant")}
        </p>

        {isUser ? (
          <p className="text-sm whitespace-pre-wrap">{message.content}</p>
        ) : (
          <div className="prose prose-sm dark:prose-invert max-w-none">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              allowedElements={ALLOWED_ELEMENTS}
              unwrapDisallowed
              components={{
                a: ({ href, children, ...props }) => {
                  // Internal citation links broadcast a "citation-jump"
                  // event so the matching source card auto-expands,
                  // then scroll to the chunk anchor inside it.
                  const isCitation = href?.startsWith("#src-");
                  if (isCitation) {
                    return (
                      <a
                        href={href}
                        className="font-semibold text-primary hover:underline no-underline mx-0.5"
                        onClick={(e) => {
                          e.preventDefault();
                          const idx = Number(
                            (href as string).replace("#src-", ""),
                          );
                          if (Number.isInteger(idx)) {
                            window.dispatchEvent(
                              new CustomEvent("citation-jump", {
                                detail: { index: idx },
                              }),
                            );
                          }
                          // Wait one frame for the parent group to
                          // expand before scrolling, otherwise the
                          // anchor may not be in the layout yet.
                          requestAnimationFrame(() => {
                            const target = document.querySelector(
                              href as string,
                            );
                            target?.scrollIntoView({
                              behavior: "smooth",
                              block: "center",
                            });
                          });
                        }}
                        {...props}
                      >
                        {children}
                      </a>
                    );
                  }
                  return (
                    <a
                      href={href}
                      target="_blank"
                      rel="noopener noreferrer nofollow"
                      {...props}
                    >
                      {children}
                    </a>
                  );
                },
              }}
            >
              {linkifyCitations(message.content, sources.length)}
            </ReactMarkdown>
          </div>
        )}

        {hasSources && <SourceCitation sources={sources} />}
        {showNoSourcesWarning && <NoSourcesWarning />}

        {canFeedback && (
          <div className="mt-2 flex gap-1">
            <Button
              variant="ghost"
              size="icon"
              className={cn(
                "h-7 w-7",
                feedback === "thumbs_up" && "text-green-500"
              )}
              disabled={feedbackLoading}
              onClick={() => handleFeedback("thumbs_up")}
              aria-label={t("helpfulResponse")}
            >
              <ThumbsUp className="h-3.5 w-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className={cn(
                "h-7 w-7",
                feedback === "thumbs_down" && "text-red-500"
              )}
              disabled={feedbackLoading}
              onClick={() => handleFeedback("thumbs_down")}
              aria-label={t("unhelpfulResponse")}
            >
              <ThumbsDown className="h-3.5 w-3.5" />
            </Button>
          </div>
        )}
      </div>

      {isUser && (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary">
          <User className="h-4 w-4 text-primary-foreground" />
        </div>
      )}
    </div>
  );
}
