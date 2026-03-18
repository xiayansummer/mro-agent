import { useState, useRef, KeyboardEvent } from "react";

interface Props {
  onSend: (message: string, imageBase64?: string, imageUrl?: string) => void;
  onStop: () => void;
  disabled: boolean;
  isLoading: boolean;
}

export default function ChatInput({ onSend, onStop, disabled, isLoading }: Props) {
  const [input, setInput] = useState("");
  const [imageBase64, setImageBase64] = useState<string | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleSend = () => {
    const trimmed = input.trim();
    if ((!trimmed && !imageBase64) || disabled) return;
    onSend(trimmed, imageBase64 ?? undefined, imageUrl ?? undefined);
    setInput("");
    setImageBase64(null);
    setImageUrl(null);
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

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const dataUrl = ev.target?.result as string;
      // dataUrl = "data:image/jpeg;base64,XXXX"
      const base64 = dataUrl.split(",")[1];
      setImageBase64(base64);
      setImageUrl(dataUrl);
    };
    reader.readAsDataURL(file);
    // Reset input so same file can be re-selected
    e.target.value = "";
  };

  const removeImage = () => {
    setImageBase64(null);
    setImageUrl(null);
  };

  const canSend = (input.trim().length > 0 || imageBase64 !== null) && !disabled;

  return (
    <div style={{
      background: "var(--surface)",
      borderTop: "1px solid var(--border)",
      padding: "12px 16px 14px",
      flexShrink: 0,
    }}>
      <div style={{ maxWidth: 780, margin: "0 auto" }}>
        {/* Image preview */}
        {imageUrl && (
          <div style={{ marginBottom: 8, display: "flex", alignItems: "flex-start", gap: 8 }}>
            <div style={{ position: "relative", display: "inline-block" }}>
              <img
                src={imageUrl}
                alt="预览"
                style={{
                  maxHeight: 80,
                  maxWidth: 120,
                  borderRadius: 6,
                  border: "1px solid var(--border)",
                  objectFit: "cover",
                }}
              />
              <button
                onClick={removeImage}
                style={{
                  position: "absolute",
                  top: -6, right: -6,
                  width: 18, height: 18,
                  borderRadius: "50%",
                  background: "#374151",
                  border: "none",
                  color: "#fff",
                  fontSize: 11,
                  cursor: "pointer",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  lineHeight: 1,
                }}
                title="移除图片"
              >
                ×
              </button>
            </div>
            <span style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
              图片已附加，可补充文字描述
            </span>
          </div>
        )}

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
          onClick={() => textareaRef.current?.focus()}
        >
          {/* Image upload button */}
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={disabled}
            title="上传图片"
            style={{
              flexShrink: 0,
              background: "none",
              border: "none",
              cursor: disabled ? "not-allowed" : "pointer",
              color: imageBase64 ? "var(--accent)" : "var(--text-muted)",
              padding: "4px 2px",
              alignSelf: "flex-end",
              marginBottom: 1,
              borderRadius: 4,
              display: "flex", alignItems: "center",
              transition: "color 0.15s",
            }}
            onMouseEnter={e => { if (!disabled) e.currentTarget.style.color = "var(--accent)"; }}
            onMouseLeave={e => { if (!imageBase64) e.currentTarget.style.color = "var(--text-muted)"; }}
          >
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2" />
              <circle cx="8.5" cy="8.5" r="1.5" />
              <path d="M21 15l-5-5L5 21" />
            </svg>
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            style={{ display: "none" }}
            onChange={handleFileChange}
          />

          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            onInput={handleInput}
            disabled={disabled}
            rows={1}
            placeholder={imageBase64 ? "补充描述（可选）..." : "描述您需要的产品，例如：M8不锈钢六角螺栓，或上传图片识别（Enter 发送）"}
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
          Enter 发送 · Shift+Enter 换行 · 支持图片识别 · 结果仅供参考
        </div>
      </div>
    </div>
  );
}
