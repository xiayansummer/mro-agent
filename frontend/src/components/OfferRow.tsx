import { useState, type CSSProperties } from "react";
import { ExternalOffer } from "../types";
import { submitExternalOfferFeedback } from "../services/api";

const PLATFORM_LABELS: Record<string, string> = {
  jd: "京东工业品",
  zkh: "震坤行",
};

interface Props {
  offer: ExternalOffer;
  sessionId?: string;
  /** Called when the user votes "disliked" — parent can hide the row (optimistic remove). */
  onDismiss?: () => void;
  /** Called when the feedback API call fails, to undo the optimistic remove. */
  onRestore?: () => void;
}

/**
 * A single offer row. Can be used standalone (e.g. inside RefinedOffersCard)
 * or inside ComparisonTable which passes onDismiss/onRestore from its own state.
 *
 * When used standalone (no onDismiss), the component manages its own
 * disliked-hide state so the "不合适" action still visually works.
 */
export default function OfferRow({ offer, sessionId, onDismiss, onRestore }: Props) {
  const [vote, setVote] = useState<"liked" | "disliked" | null>(null);
  // Self-contained dismissed state for standalone use (when parent passes no onDismiss)
  const [selfDismissed, setSelfDismissed] = useState(false);

  const handleVote = async (action: "liked" | "disliked") => {
    setVote(action);
    if (action === "disliked") {
      if (onDismiss) {
        onDismiss();
      } else {
        setSelfDismissed(true);
      }
    }
    if (!sessionId) return;
    const ok = await submitExternalOfferFeedback(sessionId, action, offer);
    if (!ok) {
      setVote(null);
      if (action === "disliked") {
        if (onRestore) {
          onRestore();
        } else {
          setSelfDismissed(false);
        }
      }
    }
  };

  // In standalone mode, hide the row if user marked it disliked
  if (selfDismissed) return null;

  return (
    <tr style={trStyle}>
      <td style={tdStyle}>
        <FeedbackButtons vote={vote} onVote={handleVote} />
      </td>
      <td style={tdStyle}>
        <div style={platformStyle}>{PLATFORM_LABELS[offer.platform] ?? offer.platform}</div>
        <div style={scoreStyle}>匹配 {Math.round(offer.matchScore || 0)}</div>
      </td>
      <td style={tdStyle}>
        <OfferThumbnail offer={offer} />
      </td>
      <td style={tdStyle}>
        <a href={offer.productUrl} target="_blank" rel="noopener noreferrer" style={titleLinkStyle}>
          {offer.title}
        </a>
      </td>
      <td style={tdStyle}>
        <div>{valueOrDash(offer.brand)}</div>
        {offer.platformSku && <div style={skuStyle}>SKU {offer.platformSku}</div>}
      </td>
      <td style={tdStyle}>
        <div>{valueOrDash(offer.specText)}</div>
        {offer.unitComparable ? (
          <div style={unitOkStyle}>单位可比</div>
        ) : (
          <div style={unitWarnStyle}>单位不可比</div>
        )}
      </td>
      <td style={{ ...tdStyle, ...priceStyle }}>
        {offer.priceText || (offer.priceValue ? `¥${offer.priceValue}` : "—")}
        {offer.unitText ? <span style={{ color: "var(--text-muted)" }}>/{offer.unitText}</span> : null}
        {offer.normalizedUnitPrice !== undefined && (
          <div style={skuStyle}>折算 ¥{offer.normalizedUnitPrice}</div>
        )}
      </td>
      <td style={tdStyle}>
        <div>{valueOrDash(offer.stockText)}</div>
        <div style={{ color: "var(--text-muted)" }}>{valueOrDash(offer.deliveryText)}</div>
      </td>
      <td style={tdStyle}>
        <div style={reasonStyle}>
          {offer.matchReasons.length > 0 ? offer.matchReasons.slice(0, 3).join("；") : "按搜索相关性保留"}
        </div>
      </td>
    </tr>
  );
}

function OfferThumbnail({ offer }: { offer: ExternalOffer }) {
  if (!offer.imageUrl) {
    return <div style={thumbnailEmptyStyle}>无图</div>;
  }
  return (
    <a href={offer.productUrl} target="_blank" rel="noopener noreferrer" style={thumbnailLinkStyle}>
      <img
        src={offer.imageUrl}
        alt={offer.title}
        loading="lazy"
        referrerPolicy="no-referrer"
        style={thumbnailImageStyle}
      />
    </a>
  );
}

function FeedbackButtons({
  vote,
  onVote,
}: {
  vote: "liked" | "disliked" | null;
  onVote: (action: "liked" | "disliked") => void;
}) {
  return (
    <div style={feedbackWrapStyle}>
      <div style={feedbackTextStyle}>
        {vote === "liked" ? "已标记合适" : vote === "disliked" ? "已标记不合适" : "是否合适？"}
      </div>
      <div style={{ display: "flex", gap: 4 }}>
        {(["liked", "disliked"] as const).map((action) => {
          const isActive = vote === action;
          const isLike = action === "liked";
          return (
            <button
              key={action}
              disabled={vote !== null}
              onClick={() => onVote(action)}
              title={isLike ? "合适" : "不合适"}
              style={feedbackButtonStyle(isActive, isLike)}
            >
              {isLike ? "✓" : "×"}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function valueOrDash(value?: string | null) {
  return value && value.trim() ? value : "—";
}

function feedbackButtonStyle(active: boolean, isLike: boolean): CSSProperties {
  return {
    width: 24,
    height: 24,
    borderRadius: 6,
    border: `1px solid ${active ? (isLike ? "#86efac" : "#fca5a5") : "var(--border)"}`,
    background: active ? (isLike ? "#dcfce7" : "#fee2e2") : "var(--surface)",
    color: active ? (isLike ? "#166534" : "#b91c1c") : "var(--text-secondary)",
    cursor: active ? "default" : "pointer",
    fontSize: 13,
    fontWeight: 700,
    lineHeight: 1,
  };
}

const feedbackWrapStyle: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 5,
};

const feedbackTextStyle: CSSProperties = {
  fontSize: 11,
  color: "var(--text-muted)",
  whiteSpace: "nowrap",
};

const trStyle: CSSProperties = {
  borderBottom: "1px solid var(--border)",
};

const tdStyle: CSSProperties = {
  padding: "10px",
  verticalAlign: "top",
  color: "var(--text-secondary)",
  lineHeight: 1.5,
};

const titleLinkStyle: CSSProperties = {
  color: "var(--text-primary)",
  textDecoration: "none",
  fontWeight: 600,
};

const thumbnailLinkStyle: CSSProperties = {
  display: "block",
  width: 54,
  height: 54,
  borderRadius: 8,
  border: "1px solid var(--border)",
  background: "#fff",
  overflow: "hidden",
};

const thumbnailImageStyle: CSSProperties = {
  width: "100%",
  height: "100%",
  objectFit: "contain",
  display: "block",
};

const thumbnailEmptyStyle: CSSProperties = {
  width: 54,
  height: 54,
  borderRadius: 8,
  border: "1px dashed var(--border)",
  color: "var(--text-muted)",
  background: "#f8fafc",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  fontSize: 11,
};

const platformStyle: CSSProperties = {
  fontSize: 11,
  color: "var(--text-muted)",
  fontFamily: "var(--mono)",
};

const scoreStyle: CSSProperties = {
  fontSize: 11,
  color: "#166534",
  background: "#dcfce7",
  borderRadius: 999,
  padding: "1px 6px",
  display: "inline-block",
  marginTop: 4,
};

const skuStyle: CSSProperties = {
  fontSize: 11,
  color: "var(--text-muted)",
  fontFamily: "var(--mono)",
};

const priceStyle: CSSProperties = {
  color: "#f59e0b",
  fontWeight: 700,
  fontFamily: "var(--mono)",
  fontSize: 13,
};

const reasonStyle: CSSProperties = {
  color: "#2563eb",
  fontSize: 11,
};

const unitOkStyle: CSSProperties = {
  color: "#166534",
  fontSize: 11,
  marginTop: 3,
};

const unitWarnStyle: CSSProperties = {
  color: "#b45309",
  fontSize: 11,
  marginTop: 3,
};
