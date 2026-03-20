import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ChatMessage } from "../types";
import SkuCard from "./SkuCard";

interface Props {
  message: ChatMessage;
  isFirst?: boolean;
  sessionId?: string;
}

export default function MessageBubble({ message, isFirst, sessionId }: Props) {
  const isUser = message.role === "user";
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = message.content;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (isUser) {
    return (
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}>
        <div style={{
          maxWidth: "72%",
          background: "#1e2334",
          color: "#e8eaf0",
          borderRadius: "12px 12px 3px 12px",
          padding: "10px 14px",
          fontSize: 14,
          lineHeight: 1.7,
          wordBreak: "break-word",
        }}>
          {message.imageUrl && (
            <img
              src={message.imageUrl}
              alt="上传图片"
              style={{
                display: "block",
                maxWidth: "100%",
                maxHeight: 200,
                borderRadius: 6,
                marginBottom: message.content ? 8 : 0,
                objectFit: "contain",
              }}
            />
          )}
          {message.content && (
            <span style={{ whiteSpace: "pre-wrap" }}>{message.content}</span>
          )}
        </div>
      </div>
    );
  }

  // Assistant message
  return (
    <div style={{ display: "flex", gap: 10, marginBottom: 16, alignItems: "flex-start" }} className="animate-fade-in msg-assistant">
      {/* Avatar */}
      <div style={{
        width: 26, height: 26,
        background: "var(--accent)",
        borderRadius: 5,
        display: "flex", alignItems: "center", justifyContent: "center",
        flexShrink: 0,
        marginTop: 3,
      }}>
        <span style={{ color: "#fff", fontWeight: 700, fontSize: 11, fontFamily: "var(--mono)" }}>AI</span>
      </div>

      {/* Content */}
      <div style={{ flex: 1, minWidth: 0 }}>
        {/* Thinking / loading */}
        {message.isStreaming && !message.content && (
          <div style={{ display: "flex", gap: 4, padding: "12px 0" }}>
            <span className="thinking-dot" />
            <span className="thinking-dot" />
            <span className="thinking-dot" />
          </div>
        )}

        {/* SKU results above text */}
        {message.skuResults && message.skuResults.length > 0 && (
          <div style={{ marginBottom: 12 }}>
            <div style={{
              fontSize: 11,
              fontFamily: "var(--mono)",
              color: "var(--text-muted)",
              marginBottom: 8,
              display: "flex", alignItems: "center", gap: 6,
            }}>
              <span style={{
                display: "inline-block",
                width: 6, height: 6,
                borderRadius: "50%",
                background: "var(--accent)",
              }} />
              找到 {message.skuResults.length} 个匹配产品
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 8 }}>
              {message.skuResults.map((sku, i) => (
                <SkuCard key={sku.item_code} sku={sku} index={i} sessionId={sessionId} />
              ))}
            </div>
          </div>
        )}

        {/* Competitor results */}
        {message.competitorResults && message.competitorResults.length > 0 && (
          <div style={{ marginBottom: 12 }}>
            <div style={{
              fontSize: 11,
              fontFamily: "var(--mono)",
              color: "var(--text-muted)",
              marginBottom: 8,
              display: "flex", alignItems: "center", gap: 6,
            }}>
              <span style={{
                display: "inline-block",
                width: 6, height: 6,
                borderRadius: "50%",
                background: "#f59e0b",
              }} />
              西域竞品参考价 ({message.competitorResults.length} 条)
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {message.competitorResults.map((item, i) => (
                <div key={i} style={{
                  background: "var(--surface)",
                  border: "1px solid var(--border)",
                  borderRadius: 6,
                  padding: "8px 12px",
                  display: "flex", alignItems: "center", gap: 12,
                  fontSize: 13,
                }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    {item.url ? (
                      <a
                        href={item.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ color: "var(--text-primary)", textDecoration: "none", fontWeight: 500 }}
                        onMouseEnter={e => (e.currentTarget.style.color = "var(--accent)")}
                        onMouseLeave={e => (e.currentTarget.style.color = "var(--text-primary)")}
                      >
                        {item.name}
                      </a>
                    ) : (
                      <span style={{ fontWeight: 500 }}>{item.name}</span>
                    )}
                    {item.sku && (
                      <span style={{ marginLeft: 8, fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--mono)" }}>
                        {item.sku}
                      </span>
                    )}
                  </div>
                  {item.price && (
                    <div style={{ flexShrink: 0, color: "#f59e0b", fontWeight: 600, fontFamily: "var(--mono)" }}>
                      ¥{item.price}{item.unit ? `/${item.unit}` : ""}
                    </div>
                  )}
                  {item.delivery && (
                    <div style={{ flexShrink: 0, fontSize: 11, color: "var(--text-muted)" }}>
                      {item.delivery}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Text content */}
        {message.content && (
          <div style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            padding: "14px 16px",
            position: "relative",
          }}>
            {message.isStreaming ? (
              <div className="md" style={{ whiteSpace: "pre-wrap" }}>
                {message.content}
                <span
                  style={{
                    display: "inline-block",
                    width: 2, height: "0.9em",
                    background: "var(--accent)",
                    marginLeft: 2,
                    verticalAlign: "middle",
                  }}
                  className="animate-blink"
                />
              </div>
            ) : (
              <>
                <div className="md">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {message.content}
                  </ReactMarkdown>
                </div>

                {/* Copy button */}
                <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 8, opacity: 0 }} className="group-hover:opacity-100 copy-btn-wrap">
                  <button
                    onClick={handleCopy}
                    style={{
                      display: "flex", alignItems: "center", gap: 4,
                      background: "none", border: "1px solid var(--border)",
                      borderRadius: 4, padding: "3px 8px",
                      color: copied ? "#16a34a" : "var(--text-muted)",
                      fontSize: 11, cursor: "pointer",
                      transition: "all 0.15s",
                    }}
                    onMouseEnter={e => (e.currentTarget.style.borderColor = "var(--border-strong)")}
                    onMouseLeave={e => (e.currentTarget.style.borderColor = "var(--border)")}
                  >
                    {copied ? (
                      <>
                        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                          <path d="M5 13l4 4L19 7" />
                        </svg>
                        已复制
                      </>
                    ) : (
                      <>
                        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                          <rect x="9" y="9" width="13" height="13" rx="2" />
                          <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
                        </svg>
                        复制
                      </>
                    )}
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
