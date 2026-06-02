import { useState, type CSSProperties } from "react";
import { ComparisonPlatform, ComparisonSubtask, ComparisonTask, ExternalOffer } from "../types";
import { submitExternalOfferFeedback } from "../services/api";

interface Props {
  task: ComparisonTask;
  sessionId?: string;
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

export default function ComparisonTaskCard({ task, sessionId, onRefresh, onRetryPlatform }: Props) {
  const offers = task.subtasks.flatMap((subtask) =>
    subtask.items.map((item) => ({ ...item, platform: subtask.platform }))
  ).sort(compareOffers);
  const progress = getTaskProgress(task);

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
          <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
            及时标记候选是否合适，反馈越多，AI 后续越懂您的采购偏好。
          </div>
        </div>
        <button onClick={onRefresh} style={buttonStyle}>刷新</button>
      </div>

      {!progress.isTerminal && (
        <TaskProgress task={task} progress={progress} />
      )}

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
        <ComparisonTable offers={offers.slice(0, 10)} sessionId={sessionId} />
      ) : (
        <div style={emptyStyle}>
          {task.status === "queued" || task.status === "running"
            ? "扩展正在查询外部平台，本卡片会自动刷新进度。"
            : "当前还没有可展示的外部候选。"}
        </div>
      )}
    </div>
  );
}

function TaskProgress({
  task,
  progress,
}: {
  task: ComparisonTask;
  progress: ReturnType<typeof getTaskProgress>;
}) {
  const activePlatforms = task.subtasks
    .filter((subtask) => ["queued", "in_progress"].includes(subtask.status))
    .map((subtask) => PLATFORM_LABELS[subtask.platform])
    .join("、");
  const updatedAt = Math.max(...task.subtasks.map((subtask) => subtask.updatedAt || subtask.createdAt || 0));

  return (
    <div style={progressWrapStyle}>
      <div style={progressHeaderStyle}>
        <span>{progress.label}</span>
        <span>{progress.doneCount}/{progress.total} 平台完成</span>
      </div>
      <div style={progressTrackStyle}>
        <div style={{ ...progressBarStyle, width: `${progress.percent}%` }} />
      </div>
      <div style={progressMetaStyle}>
        <span>{activePlatforms ? `正在处理：${activePlatforms}` : "正在汇总结果"}</span>
        {updatedAt > 0 && <span>最近更新 {formatElapsed(updatedAt)}</span>}
      </div>
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
  const retryable = isRetryableSubtask(subtask);
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
  if (isHeartbeatLoginRequired(subtask)) {
    return `${PLATFORM_LABELS[subtask.platform]}：平台未登录或登录态未知。请先在 Chrome 扩展里完成平台登录并点击“立即上报状态”，然后刷新本卡片。`;
  }
  if (isJdBlockedByVerification(subtask)) {
    return "京东工业品：当前触发登录/安全验证。扩展会保留京东验证页，请先在插件里打开并完成验证，然后回到本卡片点击重试。";
  }
  return `${PLATFORM_LABELS[subtask.platform]}：${message}`;
}

function isRetryableSubtask(subtask: ComparisonSubtask) {
  if (isHeartbeatLoginRequired(subtask)) return false;
  return ["login_required", "failed", "timeout"].includes(subtask.status);
}

function isHeartbeatLoginRequired(subtask: ComparisonSubtask) {
  const message = `${subtask.error?.message || ""} ${subtask.error?.code || ""}`;
  return (
    subtask.status === "login_required"
    && /login_required|平台未登录|登录态未知|extension_offline|Chrome 扩展未在线/i.test(message)
  );
}

function isJdBlockedByVerification(subtask: ComparisonSubtask) {
  const message = `${subtask.error?.message || ""} ${subtask.error?.code || ""}`;
  return (
    subtask.platform === "jd"
    && ["failed", "login_required", "timeout"].includes(subtask.status)
    && /未解析到搜索结果|登录|验证|captcha|安全验证|风控|重定向/i.test(message)
  );
}

function ComparisonTable({ offers, sessionId }: { offers: ExternalOffer[]; sessionId?: string }) {
  return (
    <div style={tableWrapStyle}>
      <table style={tableStyle}>
        <thead>
          <tr>
            <Th width={90}>反馈</Th>
            <Th width={74}>平台</Th>
            <Th width={72}>图片</Th>
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
            <OfferRow key={`${offer.platform}-${offer.id}`} offer={offer} sessionId={sessionId} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Th({ children, width }: { children: string; width?: number }) {
  return <th style={{ ...thStyle, width }}>{children}</th>;
}

function OfferRow({ offer, sessionId }: { offer: ExternalOffer; sessionId?: string }) {
  const [vote, setVote] = useState<"liked" | "disliked" | null>(null);

  const handleVote = (action: "liked" | "disliked") => {
    setVote(action);
    if (sessionId) submitExternalOfferFeedback(sessionId, action, offer);
  };

  return (
    <tr style={trStyle}>
      <td style={tdStyle}>
        <FeedbackButtons vote={vote} onVote={handleVote} />
      </td>
      <td style={tdStyle}>
        <div style={platformStyle}>{PLATFORM_LABELS[offer.platform]}</div>
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

function getTaskProgress(task: ComparisonTask) {
  const total = Math.max(task.subtasks.length, 1);
  const doneCount = task.subtasks.filter((subtask) => subtask.status === "done").length;
  const failedCount = task.subtasks.filter((subtask) =>
    ["failed", "timeout", "login_required"].includes(subtask.status)
  ).length;
  const runningCount = task.subtasks.filter((subtask) => subtask.status === "in_progress").length;
  const queuedCount = task.subtasks.filter((subtask) => subtask.status === "queued").length;
  const weighted = doneCount + failedCount + runningCount * 0.55 + queuedCount * 0.2;
  const percent = Math.max(8, Math.min(98, Math.round((weighted / total) * 100)));
  const isTerminal = ["done", "failed", "cancelled"].includes(task.status)
    || task.subtasks.every((subtask) => ["done", "failed", "timeout", "login_required"].includes(subtask.status));
  let label = "正在比价";
  if (runningCount > 0) label = "Chrome 扩展正在抓取搜索结果";
  else if (queuedCount > 0) label = "等待 Chrome 扩展领取任务";
  else if (failedCount > 0) label = "部分平台需要处理";
  return { doneCount, failedCount, isTerminal, label, percent, total };
}

function formatElapsed(timestamp: number) {
  const seconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000));
  if (seconds < 5) return "刚刚";
  if (seconds < 60) return `${seconds} 秒前`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes} 分钟前`;
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

const progressWrapStyle: CSSProperties = {
  background: "#f8fafc",
  border: "1px solid var(--border)",
  borderRadius: 8,
  padding: "9px 10px",
  marginBottom: 10,
};

const progressHeaderStyle: CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  gap: 12,
  color: "var(--text-secondary)",
  fontSize: 12,
  fontWeight: 700,
  marginBottom: 7,
};

const progressTrackStyle: CSSProperties = {
  height: 6,
  borderRadius: 999,
  background: "#e5e7eb",
  overflow: "hidden",
};

const progressBarStyle: CSSProperties = {
  height: "100%",
  borderRadius: 999,
  background: "linear-gradient(90deg, #2563eb, #22c55e)",
  transition: "width 240ms ease",
};

const progressMetaStyle: CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  gap: 12,
  color: "var(--text-muted)",
  fontSize: 11,
  marginTop: 7,
  flexWrap: "wrap",
};

const tableWrapStyle: CSSProperties = {
  overflowX: "auto",
  border: "1px solid var(--border)",
  borderRadius: 8,
  background: "var(--bg)",
};

const tableStyle: CSSProperties = {
  width: "100%",
  minWidth: 840,
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
