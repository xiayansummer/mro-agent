import { useState, useRef, KeyboardEvent } from "react";

interface Props {
  onSend: (message: string) => void;
  onStop: () => void;
  disabled: boolean;
  isLoading: boolean;
}

export default function ChatInput({ onSend, onStop, disabled, isLoading }: Props) {
  const [input, setInput] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  };

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = () => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 120) + "px";
    }
  };

  const canSend = input.trim().length > 0;

  return (
    <div style={{
      background: "var(--surface)",
      borderTop: "1px solid var(--border)",
      padding: "12px 16px 14px",
      flexShrink: 0,
    }}>
      <div style={{ maxWidth: 780, margin: "0 auto" }}>
        <div style={{
          display: "flex",
          gap: 8,
          alignItems: "flex-end",
          background: disabled ? "#f8f9fb" : "#fff",
          border: "1px solid",
          borderColor: disabled ? "var(--border)" : "var(--border-strong)",
          borderRadius: 8,
          padding: "8px 10px 8px 14px",
          transition: "border-color 0.15s, box-shadow 0.15s",
        }}
          onFocus={() => {}}
          onClick={() => textareaRef.current?.focus()}
        >
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            onInput={handleInput}
            disabled={disabled}
            rows={1}
            placeholder="描述您需要的产品，例如：M8不锈钢六角螺栓（Enter 发送，Shift+Enter 换行）"
            style={{
              flex: 1,
              resize: "none",
              border: "none",
              outline: "none",
              background: "transparent",
              fontSize: 14,
              lineHeight: 1.65,
              color: "var(--text-primary)",
              fontFamily: "var(--sans)",
              minHeight: 22,
            }}
            className="placeholder:text-gray-400"
          />

          {isLoading ? (
            <button
              onClick={onStop}
              style={{
                flexShrink: 0,
                background: "#fee2e2",
                color: "#dc2626",
                border: "1px solid #fecaca",
                borderRadius: 6,
                padding: "5px 14px",
                fontSize: 13,
                fontWeight: 500,
                cursor: "pointer",
                transition: "all 0.15s",
                alignSelf: "flex-end",
              }}
              onMouseEnter={e => (e.currentTarget.style.background = "#fecaca")}
              onMouseLeave={e => (e.currentTarget.style.background = "#fee2e2")}
            >
              停止
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!canSend}
              style={{
                flexShrink: 0,
                background: canSend ? "var(--accent)" : "var(--border)",
                color: canSend ? "#fff" : "var(--text-muted)",
                border: "none",
                borderRadius: 6,
                padding: "6px 16px",
                fontSize: 13,
                fontWeight: 500,
                cursor: canSend ? "pointer" : "not-allowed",
                transition: "all 0.15s",
                alignSelf: "flex-end",
              }}
              onMouseEnter={e => { if (canSend) (e.currentTarget as HTMLButtonElement).style.background = "#c0521f"; }}
              onMouseLeave={e => { if (canSend) (e.currentTarget as HTMLButtonElement).style.background = "var(--accent)"; }}
            >
              发送
            </button>
          )}
        </div>

        <div style={{
          marginTop: 6,
          fontSize: 11,
          color: "var(--text-muted)",
          textAlign: "center",
        }}>
          Enter 发送 · Shift+Enter 换行 · 结果仅供参考
        </div>
      </div>
    </div>
  );
}
