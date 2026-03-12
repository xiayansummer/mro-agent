import { useState, useRef, useEffect, useCallback } from "react";
import { ChatMessage } from "../types";
import { sendMessage } from "../services/api";
import MessageBubble from "./MessageBubble";
import ChatInput from "./ChatInput";

function generateId() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2);
}

const WELCOME_MESSAGE: ChatMessage = {
  id: "welcome",
  role: "assistant",
  content:
    "您好！我是 MRO 紧固件 AI 助手，可以帮您快速找到合适的工业品。\n\n您可以直接告诉我需要什么产品，例如：\n- M8不锈钢六角螺栓\n- 304材质的法兰螺母\n- 固定钢板用什么螺丝好\n\n请问您需要找什么产品？",
};

interface Props {
  sessionId: string;
  messages: ChatMessage[];
  onMessagesChange: (msgs: ChatMessage[]) => void;
  onToggleSidebar: () => void;
}

export default function ChatWindow({
  sessionId,
  messages,
  onMessagesChange,
  onToggleSidebar,
}: Props) {
  const [isLoading, setIsLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const messagesRef = useRef(messages);
  messagesRef.current = messages;
  const abortRef = useRef<AbortController | null>(null);

  const updateMessages = useCallback(
    (msgs: ChatMessage[]) => {
      messagesRef.current = msgs;
      onMessagesChange(msgs);
    },
    [onMessagesChange]
  );

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  // Cleanup abort on unmount
  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  // Track if user has scrolled up
  const [showScrollBtn, setShowScrollBtn] = useState(false);
  const messagesContainerRef = useRef<HTMLDivElement>(null);

  const handleScroll = useCallback(() => {
    const el = messagesContainerRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    setShowScrollBtn(distanceFromBottom > 150);
  }, []);

  const displayMessages =
    messages.length === 0 ? [WELCOME_MESSAGE] : messages;

  const handleStop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const handleSend = async (text: string) => {
    const userMsg: ChatMessage = {
      id: generateId(),
      role: "user",
      content: text,
    };
    const assistantMsgId = generateId();
    const assistantMsg: ChatMessage = {
      id: assistantMsgId,
      role: "assistant",
      content: "",
      isStreaming: true,
    };

    const updated = [...messagesRef.current, userMsg, assistantMsg];
    updateMessages(updated);
    setIsLoading(true);

    const abortController = new AbortController();
    abortRef.current = abortController;

    try {
      await sendMessage(
        sessionId,
        text,
        {
          onText: (chunk) => {
            const next = messagesRef.current.map((m) =>
              m.id === assistantMsgId
                ? { ...m, content: m.content + chunk }
                : m
            );
            updateMessages(next);
          },
          onSkuResults: (results) => {
            const next = messagesRef.current.map((m) =>
              m.id === assistantMsgId ? { ...m, skuResults: results } : m
            );
            updateMessages(next);
          },
          onThinking: (msg) => {
            const next = messagesRef.current.map((m) =>
              m.id === assistantMsgId && !m.content
                ? { ...m, content: msg }
                : m
            );
            updateMessages(next);
          },
          onDone: () => {
            const next = messagesRef.current.map((m) =>
              m.id === assistantMsgId
                ? { ...m, isStreaming: false }
                : m
            );
            updateMessages(next);
            setIsLoading(false);
          },
          onError: (err) => {
            const next = messagesRef.current.map((m) =>
              m.id === assistantMsgId
                ? {
                    ...m,
                    content: m.content
                      ? m.content + `\n\n⚠ ${err}`
                      : `⚠ ${err}`,
                    isStreaming: false,
                  }
                : m
            );
            updateMessages(next);
            setIsLoading(false);
          },
        },
        abortController.signal
      );
    } catch (err: unknown) {
      // Aborted by user
      if (err instanceof DOMException && err.name === "AbortError") {
        const next = messagesRef.current.map((m) =>
          m.id === assistantMsgId ? { ...m, isStreaming: false } : m
        );
        updateMessages(next);
        setIsLoading(false);
        return;
      }
      // Network error
      const errorMsg =
        err instanceof Error ? err.message : "网络连接失败，请检查网络后重试";
      const next = messagesRef.current.map((m) =>
        m.id === assistantMsgId
          ? { ...m, content: `⚠ ${errorMsg}`, isStreaming: false }
          : m
      );
      updateMessages(next);
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-gray-50 flex-1 min-w-0">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-4 py-3 shrink-0">
        <div className="max-w-3xl mx-auto flex items-center gap-3">
          <button
            onClick={onToggleSidebar}
            className="md:hidden p-1.5 -ml-1.5 rounded-lg hover:bg-gray-100 text-gray-600"
          >
            <svg
              className="w-5 h-5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 6h16M4 12h16M4 18h16"
              />
            </svg>
          </button>
          <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
            <span className="text-white font-bold text-sm">M</span>
          </div>
          <div>
            <h1 className="text-base font-semibold text-gray-900">
              MRO 紧固件 AI 助手
            </h1>
            <p className="text-xs text-gray-500">
              智能产品推荐 · 200万+ SKU
            </p>
          </div>
        </div>
      </header>

      {/* Messages */}
      <div
        ref={messagesContainerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto px-4 py-4 relative"
      >
        <div className="max-w-3xl mx-auto">
          {displayMessages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}
          <div ref={bottomRef} />
        </div>

        {/* Scroll to bottom button */}
        {showScrollBtn && (
          <button
            onClick={scrollToBottom}
            className="fixed bottom-24 right-6 w-10 h-10 bg-white border border-gray-200 rounded-full shadow-lg flex items-center justify-center text-gray-500 hover:text-gray-700 hover:shadow-xl transition-all z-10"
            title="滚动到底部"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
            </svg>
          </button>
        )}
      </div>

      {/* Input */}
      <ChatInput
        onSend={handleSend}
        onStop={handleStop}
        disabled={isLoading}
        isLoading={isLoading}
      />
    </div>
  );
}
