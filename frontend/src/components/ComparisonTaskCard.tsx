import type { CSSProperties } from "react";
import { ComparisonPlatform, ComparisonSubtask, ComparisonTask, ExternalOffer } from "../types";

interface Props {
  task: ComparisonTask;
  onRefresh?: () => void;
  onRetryPlatform?: (platform: ComparisonPlatform) => void;
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

export default function ComparisonTaskCard({ task, onRefresh, onRetryPlatform }: Props) {
  const offers = task.subtasks.flatMap((subtask) =>
    subtask.items.map((item) => ({ ...item, platform: subtask.platform }))
  ).sort(compareOffers);

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
          <PlatformStatusChip
            key={subtask.id}
            subtask={subtask}
            onRetryPlatform={onRetryPlatform}
          />
        ))}
      </div>

      {task.subtasks.some((subtask) => subtask.error) && (
        <div style={errorStyle}>
          {task.subtasks
            .filter((subtask) => subtask.error)
            .map(formatSubtaskError)
            .join("；")}
        </div>
      )}

      {offers.length > 0 ? (
        <ComparisonTable offers={offers.slice(0, 10)} />
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

function PlatformStatusChip({
  subtask,
  onRetryPlatform,
}: {
  subtask: ComparisonSubtask;
  onRetryPlatform?: (platform: ComparisonPlatform) => void;
}) {
  const retryable = ["login_required", "failed", "timeout"].includes(subtask.status);
  return (
    <span style={statusChipStyle(subtask.status)}>
      {PLATFORM_LABELS[subtask.platform]} · {STATUS_LABELS[subtask.status] || subtask.status}
      {subtask.items.length ? ` · ${subtask.items.length} 条` : ""}
      {retryable && (
        <button
          onClick={() => onRetryPlatform?.(subtask.platform)}
          style={retryButtonStyle}
        >
          重试
        </button>
      )}
    </span>
  );
}

function formatSubtaskError(subtask: ComparisonSubtask) {
  const message = subtask.error?.message || subtask.error?.code || "执行失败";
  if (
    subtask.platform === "jd"
    && subtask.status === "failed"
    && /未解析到搜索结果|登录|验证|captcha|安全验证/i.test(message)
  ) {
    return "京东工业品：可能需要重新验证登录态。请在 Chrome 扩展中打开京东登录，完成后点击“立即上报状态”，再回到本卡片重试。";
  }
  return `${PLATFORM_LABELS[subtask.platform]}：${message}`;
}

function ComparisonTable({ offers }: { offers: ExternalOffer[] }) {
  return (
    <div style={tableWrapStyle}>
      <table style={tableStyle}>
        <thead>
          <tr>
            <Th width={74}>平台</Th>
            <Th>候选商品</Th>
            <Th width={92}>品牌/SKU</Th>
            <Th width={120}>规格</Th>
            <Th width={96}>价格</Th>
            <Th width={92}>库存/货期</Th>
            <Th width={150}>匹配原因</Th>
          </tr>
        </thead>
        <tbody>
          {offers.map((offer) => (
            <OfferRow key={`${offer.platform}-${offer.id}`} offer={offer} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Th({ children, width }: { children: string; width?: number }) {
  return <th style={{ ...thStyle, width }}>{children}</th>;
}

function OfferRow({ offer }: { offer: ExternalOffer }) {
  return (
    <tr style={trStyle}>
      <td style={tdStyle}>
        <div style={platformStyle}>{PLATFORM_LABELS[offer.platform]}</div>
        <div style={scoreStyle}>匹配 {Math.round(offer.matchScore || 0)}</div>
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

function compareOffers(a: ExternalOffer, b: ExternalOffer) {
  const scoreDiff = (b.matchScore || 0) - (a.matchScore || 0);
  if (Math.abs(scoreDiff) >= 0.01) return scoreDiff;
  return priceSortValue(a) - priceSortValue(b);
}

function priceSortValue(offer: ExternalOffer) {
  if (offer.unitComparable && offer.normalizedUnitPrice !== undefined) return offer.normalizedUnitPrice;
  if (offer.priceValue !== undefined) return offer.priceValue * 1.2;
  return Number.MAX_SAFE_INTEGER;
}

function valueOrDash(value?: string | null) {
  return value && value.trim() ? value : "—";
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

const retryButtonStyle: CSSProperties = {
  marginLeft: 6,
  border: "none",
  background: "transparent",
  color: "inherit",
  fontSize: 11,
  fontWeight: 700,
  cursor: "pointer",
  padding: 0,
  textDecoration: "underline",
};

const tableWrapStyle: CSSProperties = {
  overflowX: "auto",
  border: "1px solid var(--border)",
  borderRadius: 8,
  background: "var(--bg)",
};

const tableStyle: CSSProperties = {
  width: "100%",
  minWidth: 760,
  borderCollapse: "collapse",
  fontSize: 12,
};

const thStyle: CSSProperties = {
  textAlign: "left",
  padding: "8px 10px",
  color: "var(--text-muted)",
  borderBottom: "1px solid var(--border)",
  fontWeight: 600,
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
