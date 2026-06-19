import { type CSSProperties } from "react";
import OfferRow from "./OfferRow";
import { ChatMessage } from "../types";

type R = NonNullable<ChatMessage["refinedOffers"]>;

export default function RefinedOffersCard({ data, sessionId }: { data: R; sessionId?: string }) {
  // offers 兜底成空数组:即便上游 payload 形状异常也不会让本卡片(进而整页)崩溃
  const offers = data.offers ?? [];
  return (
    <div style={wrapStyle}>
      <div style={headerStyle}>{data.operationLabel}（{offers.length} 条）</div>
      <div style={tableWrapStyle}>
        <table style={tableStyle}>
          <thead>
            <tr>
              <th style={thStyle}>反馈</th>
              <th style={thStyle}>平台</th>
              <th style={thStyle}>图片</th>
              <th style={thStyle}>候选商品</th>
              <th style={thStyle}>品牌/SKU</th>
              <th style={thStyle}>规格</th>
              <th style={thStyle}>价格</th>
              <th style={thStyle}>库存/货期</th>
              <th style={thStyle}>匹配原因</th>
            </tr>
          </thead>
          <tbody>
            {offers.map((o) => (
              <OfferRow key={o.id} offer={o} sessionId={sessionId} />
            ))}
          </tbody>
        </table>
      </div>
      {data.note && <div style={noteStyle}>{data.note}</div>}
    </div>
  );
}

const wrapStyle: CSSProperties = {
  border: "1px solid var(--border)",
  borderRadius: 8,
  padding: 12,
  marginTop: 8,
  background: "var(--surface)",
};

const headerStyle: CSSProperties = {
  fontWeight: 600,
  fontSize: 13,
  marginBottom: 8,
  color: "var(--text-primary)",
};

const tableWrapStyle: CSSProperties = {
  overflowX: "auto",
  border: "1px solid var(--border)",
  borderRadius: 6,
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

const noteStyle: CSSProperties = {
  fontSize: 11,
  color: "var(--text-muted)",
  marginTop: 6,
};
