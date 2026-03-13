import { SkuItem } from "../types";

interface Props {
  sku: SkuItem;
  index: number;
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

export default function SkuCard({ sku, index }: Props) {
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
    </div>
  );
}
