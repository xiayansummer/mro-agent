import type { CSSProperties } from "react";
import { ComparisonPlatform, ComparisonSubtask, ComparisonTask, ExternalOffer } from "../types";

interface Props {
  task: ComparisonTask;
  onRefresh?: () => void;
}

const PLATFORM_LABELS: Record<ComparisonPlatform, string> = {
  jd: "京东工业品",
  zkh: "震坤行",
};

const STATUS_LABELS: Record<string, string> = {
  queued: "排队中",
  running: "查询中",
  partial: "部分完成",
  done: "已完成",
  failed: "失败",
  cancelled: "已取消",
  in_progress: "查询中",
  login_required: "需要登录",
  timeout: "超时",
};

export default function ComparisonTaskCard({ task, onRefresh }: Props) {
  const offers = task.subtasks.flatMap((subtask) =>
    subtask.items.map((item) => ({ ...item, platform: subtask.platform }))
  ).sort((a, b) => (b.matchScore || 0) - (a.matchScore || 0));

  return (
    <div style={cardStyle}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text-primary)" }}>
            外部平台比价任务
          </div>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 3 }}>
            默认按匹配度排序，价格仅作辅助参考。
          </div>
        </div>
        <button onClick={onRefresh} style={buttonStyle}>刷新</button>
      </div>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: offers.length ? 12 : 0 }}>
        {task.subtasks.map((subtask) => (
          <span key={subtask.id} style={statusChipStyle(subtask.status)}>
            {PLATFORM_LABELS[subtask.platform]} · {STATUS_LABELS[subtask.status] || subtask.status}
            {subtask.items.length ? ` · ${subtask.items.length} 条` : ""}
          </span>
        ))}
      </div>

      {task.subtasks.some((subtask) => subtask.error) && (
        <div style={errorStyle}>
          {task.subtasks
            .filter((subtask) => subtask.error)
            .map((subtask) => `${PLATFORM_LABELS[subtask.platform]}：${subtask.error?.message || subtask.error?.code || "执行失败"}`)
            .join("；")}
        </div>
      )}

      {offers.length > 0 ? (
        <div style={{ display: "grid", gap: 8 }}>
          {offers.slice(0, 10).map((offer) => (
            <OfferRow key={`${offer.platform}-${offer.id}`} offer={offer} />
          ))}
        </div>
      ) : (
        <div style={emptyStyle}>
          {task.status === "queued" || task.status === "running"
            ? "扩展正在查询外部平台，稍后刷新查看结果。"
            : "当前还没有可展示的外部候选。"}
        </div>
      )}
    </div>
  );
}

function OfferRow({ offer }: { offer: ExternalOffer }) {
  return (
    <a href={offer.productUrl} target="_blank" rel="noopener noreferrer" style={offerStyle}>
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 3 }}>
          <span style={platformStyle}>{PLATFORM_LABELS[offer.platform]}</span>
          <span style={scoreStyle}>匹配 {Math.round(offer.matchScore || 0)}</span>
          {offer.platformSku && <span style={skuStyle}>SKU {offer.platformSku}</span>}
        </div>
        <div style={{ fontSize: 13, color: "var(--text-primary)", fontWeight: 600, lineHeight: 1.5 }}>
          {offer.title}
        </div>
        <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>
          {[offer.brand, offer.specText, offer.stockText, offer.deliveryText].filter(Boolean).join(" · ") || "规格信息以外部平台为准"}
        </div>
        {offer.matchReasons.length > 0 && (
          <div style={{ fontSize: 11, color: "#2563eb", marginTop: 4 }}>
            {offer.matchReasons.slice(0, 3).join("；")}
          </div>
        )}
      </div>
      <div style={priceStyle}>
        {offer.priceText || (offer.priceValue ? `¥${offer.priceValue}` : "价格待确认")}
        {offer.unitText ? <span style={{ color: "var(--text-muted)" }}>/{offer.unitText}</span> : null}
      </div>
    </a>
  );
}

function statusChipStyle(status: string): CSSProperties {
  const warn = status === "login_required" || status === "failed" || status === "timeout";
  const done = status === "done";
  return {
    fontSize: 11,
    borderRadius: 999,
    padding: "3px 8px",
    background: done ? "#dcfce7" : warn ? "#fef2f2" : "#eff6ff",
    color: done ? "#166534" : warn ? "#b91c1c" : "#1d4ed8",
    border: `1px solid ${done ? "#bbf7d0" : warn ? "#fecaca" : "#bfdbfe"}`,
  };
}

const cardStyle: CSSProperties = {
  background: "var(--surface)",
  border: "1px solid var(--border)",
  borderRadius: 10,
  padding: 14,
  boxShadow: "0 1px 2px rgba(15, 23, 42, 0.04)",
};

const buttonStyle: CSSProperties = {
  alignSelf: "flex-start",
  border: "1px solid var(--border)",
  borderRadius: 6,
  background: "var(--bg)",
  color: "var(--text-secondary)",
  padding: "4px 8px",
  fontSize: 12,
  cursor: "pointer",
};

const offerStyle: CSSProperties = {
  display: "flex",
  gap: 12,
  alignItems: "flex-start",
  padding: "10px 12px",
  border: "1px solid var(--border)",
  borderRadius: 8,
  background: "var(--bg)",
  textDecoration: "none",
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
};

const skuStyle: CSSProperties = {
  fontSize: 11,
  color: "var(--text-muted)",
  fontFamily: "var(--mono)",
};

const priceStyle: CSSProperties = {
  flexShrink: 0,
  color: "#f59e0b",
  fontWeight: 700,
  fontFamily: "var(--mono)",
  fontSize: 13,
};

const errorStyle: CSSProperties = {
  background: "#fef2f2",
  border: "1px solid #fecaca",
  color: "#b91c1c",
  borderRadius: 8,
  padding: "8px 10px",
  fontSize: 12,
  marginBottom: 10,
};

const emptyStyle: CSSProperties = {
  fontSize: 12,
  color: "var(--text-muted)",
  background: "var(--bg)",
  border: "1px dashed var(--border)",
  borderRadius: 8,
  padding: 12,
};
