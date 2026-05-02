import { useState } from "react";
import { SlotClarification } from "../types";

interface Props {
  slot: SlotClarification;
  disabled?: boolean;       // true when submitted (read-only)
  onSubmit: (composedText: string) => void;
}

/** Strip trailing "(N)" count suffix from chip text before submission. */
function cleanChipText(s: string): string {
  return s.replace(/\s*\(\d+\)$/, "");
}

export default function SlotClarificationCard({ slot, disabled = false, onSubmit }: Props) {
  // selected: { dimension key → chosen option text }
  const [selected, setSelected] = useState<Record<string, string>>({});
  const [freeText, setFreeText] = useState("");

  const isLocked = disabled || !!slot.submitted;

  const handleChipClick = (dimKey: string, option: string) => {
    if (isLocked) return;
    setSelected(prev => {
      // Same-dim single select: if clicking the already-selected, deselect; else replace
      if (prev[dimKey] === option) {
        const next = { ...prev };
        delete next[dimKey];
        return next;
      }
      return { ...prev, [dimKey]: option };
    });
  };

  const handleRemoveTag = (dimKey: string) => {
    if (isLocked) return;
    setSelected(prev => {
      const next = { ...prev };
      delete next[dimKey];
      return next;
    });
  };

  const handleSubmit = () => {
    if (isLocked) return;
    const tagTexts = Object.values(selected).map(cleanChipText);
    const composed = [...tagTexts, freeText.trim()].filter(Boolean).join(" ");
    if (!composed) return;
    onSubmit(composed);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleSubmit();
    }
  };

  const cardStyle: React.CSSProperties = {
    background: "var(--surface)",
    border: "1px solid var(--border)",
    borderRadius: 8,
    padding: 14,
    fontSize: 14,
    opacity: isLocked ? 0.85 : 1,
  };

  const chipBase: React.CSSProperties = {
    display: "inline-block",
    padding: "5px 12px",
    margin: "3px 6px 3px 0",
    borderRadius: 16,
    border: "1px solid var(--border)",
    fontSize: 13,
    cursor: isLocked ? "default" : "pointer",
    userSelect: "none",
    background: "transparent",
    color: "var(--text-primary)",
    transition: "all 0.15s",
  };

  const chipSelected: React.CSSProperties = {
    ...chipBase,
    background: "rgba(124, 58, 237, 0.15)",
    borderColor: "var(--accent, #7c3aed)",
    color: "var(--accent, #7c3aed)",
    fontWeight: 500,
  };

  const tagPill: React.CSSProperties = {
    display: "inline-flex",
    alignItems: "center",
    gap: 4,
    padding: "3px 6px 3px 10px",
    margin: "2px 4px 2px 0",
    borderRadius: 14,
    background: "rgba(124, 58, 237, 0.12)",
    color: "var(--accent, #7c3aed)",
    fontSize: 12,
  };

  return (
    <div style={cardStyle}>
      {/* Summary */}
      <div style={{ marginBottom: 8 }}>
        <span style={{ fontWeight: 600 }}>需求概述: </span>
        <span>{slot.summary}</span>
      </div>

      {/* Known params */}
      {slot.known.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>已知参数:</div>
          <ul style={{ margin: 0, paddingLeft: 20, color: "var(--text-secondary)" }}>
            {slot.known.map((k, i) => (
              <li key={i}>
                <span style={{ color: "var(--text-muted)" }}>{k.label}: </span>
                <span>{k.value}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Missing dimensions: each as chip group */}
      {slot.missing.map(dim => (
        <div key={dim.key} style={{ marginBottom: 10 }}>
          <div style={{ marginBottom: 4 }}>
            <span style={{ marginRight: 6 }}>{dim.icon}</span>
            <span>{dim.question}</span>
          </div>
          <div>
            {dim.options.map(opt => (
              <span
                key={opt}
                style={selected[dim.key] === opt ? chipSelected : chipBase}
                onClick={() => handleChipClick(dim.key, opt)}
              >
                {opt}
              </span>
            ))}
          </div>
        </div>
      ))}

      {/* Tag pill area + input — only when not locked */}
      {!isLocked && (
        <div style={{ borderTop: "1px solid var(--border)", paddingTop: 10, marginTop: 8 }}>
          {Object.keys(selected).length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <span style={{ fontSize: 12, color: "var(--text-muted)", marginRight: 6 }}>已选:</span>
              {Object.entries(selected).map(([key, val]) => (
                <span key={key} style={tagPill}>
                  {cleanChipText(val)}
                  <button
                    onClick={() => handleRemoveTag(key)}
                    style={{
                      background: "none", border: "none", color: "inherit",
                      cursor: "pointer", padding: "0 4px", fontSize: 14,
                    }}
                    aria-label="移除"
                  >
                    ✕
                  </button>
                </span>
              ))}
            </div>
          )}
          <div style={{ display: "flex", gap: 8 }}>
            <input
              type="text"
              value={freeText}
              onChange={e => setFreeText(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="自由补充（如长度 50mm、急用…）"
              style={{
                flex: 1,
                padding: "6px 10px",
                border: "1px solid var(--border)",
                borderRadius: 6,
                background: "var(--bg)",
                color: "var(--text-primary)",
                fontSize: 13,
                outline: "none",
              }}
            />
            <button
              onClick={handleSubmit}
              disabled={Object.keys(selected).length === 0 && !freeText.trim()}
              style={{
                padding: "6px 14px",
                border: "none",
                borderRadius: 6,
                background: "var(--accent, #7c3aed)",
                color: "#fff",
                cursor: "pointer",
                fontSize: 13,
                opacity: (Object.keys(selected).length === 0 && !freeText.trim()) ? 0.5 : 1,
              }}
            >
              提交
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
