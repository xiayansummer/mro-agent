import { useState } from "react";
import { SkuItem } from "../types";
import { submitFeedback } from "../services/api";

interface Props {
  sku: SkuItem;
  index: number;
  sessionId?: string;
}

const FILE_STYLE: Record<string, { bg: string; color: string }> = {
  "认证证书": { bg: "#f0fdf4", color: "#15803d" },
  "技术资料": { bg: "#eff6ff", color: "#1d4ed8" },
  "检测报告": { bg: "#fff7ed", color: "#c2410c" },
  "相关文档": { bg: "#faf5ff", color: "#7e22ce" },
};

function parseAttributes(details: string | null): { key: string; value: string }[] {
  if (!details) return [];
  return details
    .split("|")
    .map((pair) => {
      const idx = pair.indexOf(":");
      if (idx < 0) return null;
      const key = pair.slice(0, idx).trim();
      const value = pair.slice(idx + 1).trim();
      return key && value ? { key, value } : null;
    })
    .filter((x): x is { key: string; value: string } => x !== null);
}

export default function SkuCard({ sku, index, sessionId }: Props) {
  const [vote, setVote] = useState<"liked" | "disliked" | null>(null);
  const attributes = parseAttributes(sku.attribute_details);
  const category = [sku.l2_category_name, sku.l3_category_name, sku.l4_category_name]
    .filter(Boolean)
    .join(" › ");

  return (
    <div style={{
      background: "var(--surface)",
      border: "1px solid var(--border)",
      borderRadius: 7,
      padding: "12px 14px",
      transition: "border-color 0.15s, box-shadow 0.15s",
      fontSize: 13,
    }}
      onMouseEnter={e => {
        (e.currentTarget as HTMLDivElement).style.borderColor = "var(--accent-border)";
        (e.currentTarget as HTMLDivElement).style.boxShadow = "0 2px 8px rgba(212,98,42,0.08)";
      }}
      onMouseLeave={e => {
        (e.currentTarget as HTMLDivElement).style.borderColor = "var(--border)";
        (e.currentTarget as HTMLDivElement).style.boxShadow = "none";
      }}
    >
      {/* Top row: index + item_code + brand */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 7 }}>
        <span style={{
          fontFamily: "var(--mono)",
          fontSize: 10,
          color: "var(--text-muted)",
          minWidth: 20,
          fontWeight: 500,
        }}>
          {String(index + 1).padStart(2, "0")}
        </span>
        <span style={{
          fontFamily: "var(--mono)",
          fontSize: 11,
          color: "var(--accent)",
          background: "var(--accent-light)",
          padding: "1px 7px",
          borderRadius: 3,
          border: "1px solid var(--accent-border)",
          letterSpacing: "0.01em",
        }}>
          {sku.item_code}
        </span>
        {sku.brand_name && (
          <span style={{
            marginLeft: "auto",
            fontSize: 11,
            color: "var(--text-secondary)",
            background: "#f5f6f9",
            padding: "1px 7px",
            borderRadius: 3,
            border: "1px solid var(--border)",
            fontWeight: 500,
          }}>
            {sku.brand_name}
          </span>
        )}
      </div>

      {/* Item name */}
      <div style={{
        fontWeight: 600,
        fontSize: 13.5,
        color: "var(--text-primary)",
        lineHeight: 1.45,
        marginBottom: 6,
        display: "-webkit-box",
        WebkitLineClamp: 2,
        WebkitBoxOrient: "vertical",
        overflow: "hidden",
      }}>
        {sku.item_name}
      </div>

      {/* Category breadcrumb */}
      {category && (
        <div style={{
          fontSize: 11,
          color: "var(--text-muted)",
          marginBottom: 7,
          display: "flex", alignItems: "center", gap: 3,
        }}>
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ flexShrink: 0 }}>
            <path strokeLinecap="round" d="M3 7h18M3 12h18M3 17h18" />
          </svg>
          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {category}
          </span>
        </div>
      )}

      {/* Spec / mfg_sku row */}
      {(sku.specification || sku.mfg_sku) && (
        <div style={{
          display: "flex", gap: 12, marginBottom: 7,
          fontSize: 12, color: "var(--text-secondary)",
        }}>
          {sku.specification && (
            <div style={{ display: "flex", gap: 4, alignItems: "baseline", minWidth: 0 }}>
              <span style={{ color: "var(--text-muted)", flexShrink: 0 }}>规格</span>
              <span style={{
                fontFamily: "var(--mono)", fontSize: 11.5,
                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
              }}>
                {sku.specification}
              </span>
            </div>
          )}
          {sku.mfg_sku && (
            <div style={{ display: "flex", gap: 4, alignItems: "baseline", flexShrink: 0 }}>
              <span style={{ color: "var(--text-muted)" }}>厂商</span>
              <span style={{ fontFamily: "var(--mono)", fontSize: 11.5 }}>{sku.mfg_sku}</span>
            </div>
          )}
        </div>
      )}

      {/* Attributes */}
      {attributes.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 7 }}>
          {attributes.slice(0, 4).map((attr, i) => (
            <span key={i} style={{
              fontSize: 11,
              color: "var(--text-secondary)",
              background: "#f5f7fb",
              padding: "2px 7px",
              borderRadius: 3,
              border: "1px solid var(--border)",
            }}>
              {attr.key}: <span style={{ fontFamily: "var(--mono)", fontSize: 10.5 }}>{attr.value}</span>
            </span>
          ))}
          {attributes.length > 4 && (
            <span style={{ fontSize: 11, color: "var(--text-muted)" }}>+{attributes.length - 4}</span>
          )}
        </div>
      )}

      {/* Files */}
      {sku.files && sku.files.length > 0 && (
        <div style={{
          paddingTop: 8,
          borderTop: "1px solid var(--border)",
          display: "flex", flexWrap: "wrap", gap: 5,
        }}>
          {sku.files.map((file, i) => {
            const style = FILE_STYLE[file.file_type_label] ?? { bg: "#f5f6f9", color: "var(--text-secondary)" };
            return (
              <a
                key={i}
                href={file.file_url}
                target="_blank"
                rel="noopener noreferrer"
                title={file.file_name}
                style={{
                  display: "inline-flex", alignItems: "center", gap: 4,
                  fontSize: 11, padding: "2px 8px",
                  background: style.bg, color: style.color,
                  borderRadius: 3,
                  border: `1px solid ${style.color}30`,
                  textDecoration: "none",
                  transition: "opacity 0.15s",
                }}
                onMouseEnter={e => (e.currentTarget.style.opacity = "0.75")}
                onMouseLeave={e => (e.currentTarget.style.opacity = "1")}
              >
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
                  <path strokeLinecap="round" d="M14 2v6h6" />
                </svg>
                {file.file_type_label}
              </a>
            );
          })}
        </div>
      )}

      {/* Feedback */}
      <div style={{
        marginTop: 8, paddingTop: 8,
        borderTop: "1px solid var(--border)",
        display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
          {vote === "liked" ? "已标记感兴趣" : vote === "disliked" ? "已标记不符合" : "这个结果有帮助吗？"}
        </span>
        <div style={{ display: "flex", gap: 4 }}>
          {(["liked", "disliked"] as const).map((action) => {
            const isActive = vote === action;
            const isLike = action === "liked";
            return (
              <button
                key={action}
                disabled={vote !== null}
                onClick={() => {
                  setVote(action);
                  if (sessionId) submitFeedback(sessionId, action, sku);
                }}
                title={isLike ? "有帮助" : "不符合需求"}
                style={{
                  display: "flex", alignItems: "center", justifyContent: "center",
                  width: 26, height: 26,
                  background: isActive ? (isLike ? "#dcfce7" : "#fee2e2") : "transparent",
                  border: `1px solid ${isActive ? (isLike ? "#86efac" : "#fca5a5") : "var(--border)"}`,
                  borderRadius: 5,
                  cursor: vote !== null ? "default" : "pointer",
                  transition: "all 0.15s",
                  color: isActive ? (isLike ? "#16a34a" : "#dc2626") : "var(--text-muted)",
                  padding: 0,
                }}
                onMouseEnter={e => {
                  if (vote !== null) return;
                  const btn = e.currentTarget;
                  btn.style.background = isLike ? "#dcfce7" : "#fee2e2";
                  btn.style.borderColor = isLike ? "#86efac" : "#fca5a5";
                  btn.style.color = isLike ? "#16a34a" : "#dc2626";
                }}
                onMouseLeave={e => {
                  if (vote !== null) return;
                  const btn = e.currentTarget;
                  btn.style.background = "transparent";
                  btn.style.borderColor = "var(--border)";
                  btn.style.color = "var(--text-muted)";
                }}
              >
                {isLike ? (
                  <svg width="13" height="13" viewBox="0 0 24 24" fill={isActive ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                    <path d="M14 9V5a3 3 0 00-3-3l-4 9v11h11.28a2 2 0 002-1.7l1.38-9a2 2 0 00-2-2.3H14z" />
                    <path d="M7 22H4a2 2 0 01-2-2v-7a2 2 0 012-2h3" />
                  </svg>
                ) : (
                  <svg width="13" height="13" viewBox="0 0 24 24" fill={isActive ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                    <path d="M10 15v4a3 3 0 003 3l4-9V2H5.72a2 2 0 00-2 1.7l-1.38 9a2 2 0 002 2.3H10z" />
                    <path d="M17 2h2.67A2.31 2.31 0 0122 4v7a2.31 2.31 0 01-2.33 2H17" />
                  </svg>
                )}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
