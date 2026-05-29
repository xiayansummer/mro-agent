import { ComparisonDraft } from "../types";
import type { CSSProperties } from "react";

interface Props {
  draft: ComparisonDraft;
  disabled?: boolean;
  onStart?: () => void;
}

const PLATFORM_LABELS: Record<string, string> = {
  jd: "京东工业品",
  zkh: "震坤行",
};

export default function ComparisonDraftCard({ draft, disabled, onStart }: Props) {
  const { structure } = draft;
  const category = structure.category;
  const spec = structure.specification;
  const constraints = structure.purchaseConstraints;
  const categoryPath = [category.l1, category.l2, category.l3, category.l4].filter(Boolean).join(" / ");
  const specRows = [
    ["产品", spec.productType],
    ["品牌", spec.brand],
    ["型号", spec.model],
    ["材质", spec.material],
    ["规格", spec.size],
    ["标准", spec.standard],
  ].filter(([, value]) => value);

  return (
    <div style={{
      background: "var(--surface)",
      border: "1px solid var(--border)",
      borderRadius: 10,
      padding: 14,
      boxShadow: "0 1px 2px rgba(15, 23, 42, 0.04)",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text-primary)" }}>
            外部平台比价草稿
          </div>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 3 }}>
            确认结构后查询京东工业品和震坤行；本库 SKU 不参与展示。
          </div>
        </div>
        <span style={{
          alignSelf: "flex-start",
          fontSize: 11,
          fontFamily: "var(--mono)",
          color: category.confidence >= 0.7 ? "#16a34a" : "#f59e0b",
          background: category.confidence >= 0.7 ? "#dcfce7" : "#fef3c7",
          borderRadius: 999,
          padding: "2px 8px",
        }}>
          类目置信度 {Math.round(category.confidence * 100)}%
        </span>
      </div>

      <div style={{ display: "grid", gap: 10 }}>
        <section>
          <div style={labelStyle}>六层结构</div>
          <div style={valueStyle}>{categoryPath || "待补充类目"}</div>
        </section>

        {specRows.length > 0 && (
          <section>
            <div style={labelStyle}>规格要素</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {specRows.map(([label, value]) => (
                <span key={label} style={chipStyle}>{label}: {value}</span>
              ))}
              {spec.attributes.map((attr) => (
                <span key={`${attr.name}-${attr.value}`} style={chipStyle}>
                  {attr.name}: {attr.value}{attr.unit ? ` ${attr.unit}` : ""}
                </span>
              ))}
            </div>
          </section>
        )}

        <section>
          <div style={labelStyle}>采购约束</div>
          <div style={valueStyle}>
            {constraints.quantity ? `数量 ${constraints.quantity}${constraints.unit || ""}` : "数量待确认"}
            {" · "}
            平台 {draft.selectedPlatforms.map((p) => PLATFORM_LABELS[p] || p).join("、")}
          </div>
        </section>

        <section>
          <div style={labelStyle}>候选搜索词</div>
          <div style={{ display: "grid", gap: 4 }}>
            {draft.selectedPlatforms.map((platform) => (
              <div key={platform} style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                <strong>{PLATFORM_LABELS[platform] || platform}：</strong>
                {(draft.searchTerms[platform] || []).join(" → ") || "待生成"}
              </div>
            ))}
          </div>
        </section>
      </div>

      <div style={{ marginTop: 12, display: "flex", justifyContent: "flex-end" }}>
        <button
          disabled={disabled}
          onClick={onStart}
          style={{
            border: "none",
            borderRadius: 8,
            background: disabled ? "var(--border)" : "var(--accent)",
            color: "#fff",
            padding: "7px 12px",
            fontSize: 13,
            fontWeight: 600,
            cursor: disabled ? "not-allowed" : "pointer",
          }}
        >
          {draft.status === "task_created" ? "已开始比价" : "确认并开始比价"}
        </button>
      </div>
    </div>
  );
}

const labelStyle: CSSProperties = {
  fontSize: 11,
  color: "var(--text-muted)",
  fontFamily: "var(--mono)",
  marginBottom: 4,
};

const valueStyle: CSSProperties = {
  fontSize: 13,
  color: "var(--text-primary)",
};

const chipStyle: CSSProperties = {
  fontSize: 12,
  color: "var(--text-primary)",
  background: "var(--bg)",
  border: "1px solid var(--border)",
  borderRadius: 999,
  padding: "3px 8px",
};
