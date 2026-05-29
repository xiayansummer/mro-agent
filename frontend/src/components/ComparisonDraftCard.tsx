import { useEffect, useState } from "react";
import { ComparisonDraft, ExtensionPairingCode, ExtensionStatus } from "../types";
import type { CSSProperties } from "react";
import { createExtensionPairingCode, getExtensionStatus } from "../services/api";

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
  const [extensionStatus, setExtensionStatus] = useState<ExtensionStatus | null>(null);
  const [pairingCode, setPairingCode] = useState<ExtensionPairingCode | null>(null);
  const [loadingCode, setLoadingCode] = useState(false);
  const [error, setError] = useState("");
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
  const needsExtension = !extensionStatus?.online;

  useEffect(() => {
    getExtensionStatus()
      .then(setExtensionStatus)
      .catch(() => setExtensionStatus(null));
  }, []);

  async function handleCreatePairingCode() {
    setLoadingCode(true);
    setError("");
    try {
      setPairingCode(await createExtensionPairingCode());
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成配对码失败");
    } finally {
      setLoadingCode(false);
    }
  }

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

        {needsExtension && (
          <section style={pairingBoxStyle}>
            <div style={labelStyle}>Chrome 扩展绑定</div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6 }}>
              未检测到在线扩展。先安装并绑定 Chrome 扩展，绑定后本查询内容会保留，可直接点击开始比价。
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 8, flexWrap: "wrap" }}>
              <button
                type="button"
                onClick={handleCreatePairingCode}
                disabled={loadingCode}
                style={secondaryButtonStyle}
              >
                {loadingCode ? "生成中..." : "生成配对码"}
              </button>
              {pairingCode && (
                <>
                  <span style={codeStyle}>{pairingCode.code}</span>
                  <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                    {new Date(pairingCode.expiresAt).toLocaleTimeString()} 前有效
                  </span>
                </>
              )}
            </div>
            <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 6 }}>
              扩展 popup 后端地址默认填 http://localhost:8000/api，输入配对码即可绑定。
            </div>
            {error && <div style={{ fontSize: 12, color: "#b91c1c", marginTop: 6 }}>{error}</div>}
          </section>
        )}
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

const pairingBoxStyle: CSSProperties = {
  border: "1px dashed var(--border)",
  borderRadius: 8,
  padding: 10,
  background: "var(--bg)",
};

const secondaryButtonStyle: CSSProperties = {
  border: "1px solid var(--border)",
  borderRadius: 6,
  background: "var(--surface)",
  color: "var(--text-primary)",
  padding: "5px 9px",
  fontSize: 12,
  cursor: "pointer",
};

const codeStyle: CSSProperties = {
  fontFamily: "var(--mono)",
  fontSize: 18,
  letterSpacing: 2,
  fontWeight: 700,
  color: "var(--accent)",
  background: "var(--surface)",
  border: "1px solid var(--border)",
  borderRadius: 6,
  padding: "4px 10px",
};
