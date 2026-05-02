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

export default function ChatWindow({ sessionId, messages, onMessagesChange, onToggleSidebar }: Props) {
  const [isLoading, setIsLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const messagesRef = useRef(messages);
  messagesRef.current = messages;
  const abortRef = useRef<AbortController | null>(null);
  const [showScrollBtn, setShowScrollBtn] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

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

  useEffect(() => { scrollToBottom(); }, [messages, scrollToBottom]);
  useEffect(() => { return () => abortRef.current?.abort(); }, []);

  const handleScroll = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    setShowScrollBtn(el.scrollHeight - el.scrollTop - el.clientHeight > 150);
  }, []);

  const displayMessages = messages.length === 0 ? [WELCOME_MESSAGE] : messages;

  const handleStop = useCallback(() => { abortRef.current?.abort(); }, []);

  const handleSend = async (text: string, imageBase64?: string, imageUrl?: string) => {
    const userMsg: ChatMessage = { id: generateId(), role: "user", content: text, imageUrl };
    const assistantMsgId = generateId();
    const assistantMsg: ChatMessage = { id: assistantMsgId, role: "assistant", content: "", isStreaming: true };

    const updated = [...messagesRef.current, userMsg, assistantMsg];
    updateMessages(updated);
    setIsLoading(true);

    const abortController = new AbortController();
    abortRef.current = abortController;

    try {
      await sendMessage(sessionId, text, {
        onText: (chunk) => {
          const next = messagesRef.current.map((m) =>
            m.id === assistantMsgId ? { ...m, content: m.content + chunk } : m
          );
          updateMessages(next);
        },
        onSkuResults: (results) => {
          const next = messagesRef.current.map((m) =>
            m.id === assistantMsgId ? { ...m, skuResults: results } : m
          );
          updateMessages(next);
        },
        onCompetitorResults: (results) => {
          const next = messagesRef.current.map((m) =>
            m.id === assistantMsgId ? { ...m, competitorResults: results } : m
          );
          updateMessages(next);
        },
        onSlotClarification: (slot) => {
          const next = messagesRef.current.map((m) =>
            m.id === assistantMsgId ? { ...m, slotClarification: slot } : m
          );
          updateMessages(next);
        },
        onThinking: (status) => {
          const next = messagesRef.current.map((m) =>
            m.id === assistantMsgId && m.content === "" ? { ...m, thinkingStatus: status } : m
          );
          updateMessages(next);
        },
        onDone: () => {
          const next = messagesRef.current.map((m) =>
            m.id === assistantMsgId ? { ...m, isStreaming: false, thinkingStatus: undefined } : m
          );
          updateMessages(next);
          setIsLoading(false);
        },
        onError: (err) => {
          const next = messagesRef.current.map((m) =>
            m.id === assistantMsgId
              ? { ...m, content: m.content ? m.content + `\n\n⚠ ${err}` : `⚠ ${err}`, isStreaming: false }
              : m
          );
          updateMessages(next);
          setIsLoading(false);
        },
      }, abortController.signal, imageBase64);
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") {
        const next = messagesRef.current.map((m) =>
          m.id === assistantMsgId ? { ...m, isStreaming: false } : m
        );
        updateMessages(next);
        setIsLoading(false);
        return;
      }
      const errorMsg = err instanceof Error ? err.message : "网络连接失败，请检查网络后重试";
      const next = messagesRef.current.map((m) =>
        m.id === assistantMsgId ? { ...m, content: `⚠ ${errorMsg}`, isStreaming: false } : m
      );
      updateMessages(next);
      setIsLoading(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", background: "var(--bg)", flex: 1, minWidth: 0 }}>
      {/* Header */}
      <header style={{
        background: "var(--surface)",
        borderBottom: "1px solid var(--border)",
        padding: "0 24px",
        height: 52,
        display: "flex",
        alignItems: "center",
        gap: 12,
        flexShrink: 0,
      }}>
        <button
          onClick={onToggleSidebar}
          className="md:hidden"
          style={{
            background: "none", border: "none", cursor: "pointer",
            color: "var(--text-secondary)", padding: 4, borderRadius: 4, marginLeft: -4,
          }}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M3 6h18M3 12h18M3 18h18" />
          </svg>
        </button>

        <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 26, height: 26,
            background: "var(--accent)",
            borderRadius: 5,
            display: "flex", alignItems: "center", justifyContent: "center",
            flexShrink: 0,
          }}>
            <span style={{ color: "#fff", fontWeight: 700, fontSize: 12, fontFamily: "var(--mono)" }}>M</span>
          </div>
          <div>
            <span style={{ fontWeight: 600, fontSize: 14, color: "var(--text-primary)" }}>
              MRO 紧固件 AI 助手
            </span>
            <span style={{
              marginLeft: 10, fontSize: 12, color: "var(--text-muted)",
              fontFamily: "var(--mono)",
            }}>
              200万+ SKU
            </span>
          </div>
        </div>

        {isLoading && (
          <div style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--accent)", fontSize: 12 }}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ animation: "spin-slow 1s linear infinite" }}>
              <path strokeLinecap="round" d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
            </svg>
            搜索中
          </div>
        )}
      </header>

      {/* Messages */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        style={{ flex: 1, overflowY: "auto", padding: "20px 16px", position: "relative" }}
      >
        <div style={{ maxWidth: 780, margin: "0 auto" }}>
          {displayMessages.map((msg, i) => (
            <MessageBubble
              key={msg.id}
              message={msg}
              isFirst={i === 0}
              sessionId={sessionId}
              onChipSubmit={(text) => handleSend(text)}
            />
          ))}
          <div ref={bottomRef} />
        </div>

        {showScrollBtn && (
          <button
            onClick={scrollToBottom}
            style={{
              position: "fixed", bottom: 88, right: 24,
              width: 34, height: 34,
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "50%",
              boxShadow: "0 2px 8px rgba(0,0,0,0.1)",
              display: "flex", alignItems: "center", justifyContent: "center",
              cursor: "pointer", color: "var(--text-secondary)",
              zIndex: 10,
            }}
            title="滚动到底部"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <path d="M6 9l6 6 6-6" />
            </svg>
          </button>
        )}
      </div>

      <ChatInput onSend={handleSend} onStop={handleStop} disabled={isLoading} isLoading={isLoading}  />
    </div>
  );
}
