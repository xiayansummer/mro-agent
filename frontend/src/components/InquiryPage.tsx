import { useState, useRef, useCallback, useEffect } from "react";
import { authHeader } from "../services/auth";

interface InquiryRow {
  index: number;
  input: { 需求品名?: string; 需求品牌?: string; 需求型号?: string; 采购数量?: string };
  matches: SkuMatch[];
  match_count: number;
  matched: boolean;
}

interface SkuMatch {
  item_code: string;
  item_name: string;
  brand_name: string | null;
  specification: string | null;
  mfg_sku: string | null;
  l2_category_name: string | null;
  l3_category_name: string | null;
}

interface InquiryResult {
  total: number;
  matched: number;
  filename: string;
  rows: InquiryRow[];
}

interface HistoryEntry {
  id: string;
  filename: string;
  total: number;
  matched: number;
  time: number;
  result: InquiryResult;
}

const HISTORY_KEY = "mro-inquiry-history";
const MAX_HISTORY = 30;

function loadHistory(): HistoryEntry[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveHistory(list: HistoryEntry[]) {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(list.slice(0, MAX_HISTORY)));
  } catch {}
}

function formatTime(ts: number) {
  return new Date(ts).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function downloadCSV(result: InquiryResult) {
  const headers = ["行号", "需求品名", "需求品牌", "需求型号", "采购数量", "匹配数", "推荐编码", "推荐产品名", "推荐品牌", "推荐规格"];
  const rows = result.rows.flatMap((row) => {
    if (row.matches.length === 0) {
      return [[row.index, row.input.需求品名 || "", row.input.需求品牌 || "", row.input.需求型号 || "", row.input.采购数量 || "", 0, "", "未找到匹配产品", "", ""]];
    }
    return row.matches.map((m, mi) => [
      mi === 0 ? row.index : "",
      mi === 0 ? row.input.需求品名 || "" : "",
      mi === 0 ? row.input.需求品牌 || "" : "",
      mi === 0 ? row.input.需求型号 || "" : "",
      mi === 0 ? row.input.采购数量 || "" : "",
      mi === 0 ? row.match_count : "",
      m.item_code, m.item_name, m.brand_name || "", m.specification || "",
    ]);
  });
  const csv = [headers, ...rows].map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(",")).join("\n");
  const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `询价结果_${result.filename.replace(/\.[^.]+$/, "")}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export default function InquiryPage({ onToggleSidebar }: { onToggleSidebar?: () => void }) {
  const [tab, setTab] = useState<"upload" | "paste">("upload");
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<InquiryResult | null>(null);
  const [error, setError] = useState("");
  const [history, setHistory] = useState<HistoryEntry[]>(() => loadHistory());
  const [pasteText, setPasteText] = useState("");
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set());
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => { saveHistory(history); }, [history]);

  const deleteHistory = useCallback((id: string) => {
    setHistory((h) => h.filter((e) => e.id !== id));
  }, []);

  const clearHistory = useCallback(() => {
    setHistory([]);
  }, []);

  const processFile = useCallback(async (file: File) => {
    if (!file.name.match(/\.(xlsx|xls|csv)$/i)) {
      setError("请上传 .xlsx、.xls 或 .csv 格式的文件");
      return;
    }
    setLoading(true);
    setError("");
    setResult(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await fetch("/api/inquiry/upload", { method: "POST", body: form, headers: authHeader() });
      if (res.status === 401) {
        window.dispatchEvent(new Event("mro:unauthorized"));
        throw new Error("登录已失效，请重新登录");
      }
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `请求失败 ${res.status}`);
      }
      const data: InquiryResult = await res.json();
      setResult(data);
      setHistory((h) => [
        { id: Date.now().toString(36), filename: file.name, total: data.total, matched: data.matched, time: Date.now(), result: data },
        ...h.slice(0, 19),
      ]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "上传失败，请重试");
    } finally {
      setLoading(false);
    }
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) processFile(file);
  }, [processFile]);

  const handlePasteSubmit = useCallback(async () => {
    if (!pasteText.trim()) return;
    // Convert paste text to CSV and submit as virtual file
    const lines = pasteText.trim().split("\n");
    const hasHeader = lines[0].includes("品名") || lines[0].includes("型号");
    const csvLines = hasHeader ? lines : ["需求品名,需求品牌,需求型号,采购数量", ...lines];
    const csvContent = csvLines.join("\n");
    const file = new File([csvContent], "paste_input.csv", { type: "text/csv" });
    await processFile(file);
  }, [pasteText, processFile]);

  const toggleRow = (idx: number) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      next.has(idx) ? next.delete(idx) : next.add(idx);
      return next;
    });
  };

  const accentColor = "var(--accent)";
  const borderColor = "var(--border)";

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", background: "var(--bg)", flex: 1, minWidth: 0, overflowY: "auto" }}>
      {/* Header */}
      <header style={{ background: "var(--surface)", borderBottom: `1px solid ${borderColor}`, padding: "0 16px 0 12px", height: 52, display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
        {onToggleSidebar && (
          <button
            onClick={onToggleSidebar}
            className="md:hidden"
            style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", padding: 6, borderRadius: 6, display: "flex" }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M3 6h18M3 12h18M3 18h18" />
            </svg>
          </button>
        )}
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ width: 26, height: 26, background: accentColor, borderRadius: 5, display: "flex", alignItems: "center", justifyContent: "center" }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinecap="round">
              <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
          </div>
          <span style={{ fontWeight: 600, fontSize: 14, color: "var(--text-primary)" }}>批量询报价</span>
          <span style={{ fontSize: 12, color: "var(--text-muted)", fontFamily: "var(--mono)" }}>最多 200 行</span>
        </div>
      </header>

      <div style={{ flex: 1, padding: "24px 28px", maxWidth: 1000, width: "100%", margin: "0 auto", boxSizing: "border-box" }}>
        {/* Steps */}
        <div style={{ display: "flex", alignItems: "center", gap: 0, marginBottom: 24 }}>
          {[
            { n: 1, label: "上传询价单" },
            { n: 2, label: "批量匹配" },
            { n: 3, label: "查看 / 导出结果" },
          ].map((step, i) => (
            <div key={step.n} style={{ display: "flex", alignItems: "center", flex: 1 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <div style={{
                  width: 24, height: 24, borderRadius: "50%",
                  background: result && i <= 2 ? accentColor : i === 0 ? accentColor : "var(--border)",
                  color: "#fff", fontSize: 12, fontWeight: 700,
                  display: "flex", alignItems: "center", justifyContent: "center",
                }}>
                  {result && i < 2 ? "✓" : step.n}
                </div>
                <span style={{ fontSize: 12.5, color: "var(--text-secondary)", fontWeight: i === 0 ? 500 : 400 }}>{step.label}</span>
              </div>
              {i < 2 && <div style={{ flex: 1, height: 1, background: "var(--border)", margin: "0 12px" }} />}
            </div>
          ))}
        </div>

        {/* Upload card */}
        {!result && (
          <div style={{ background: "var(--surface)", border: `1px solid ${borderColor}`, borderRadius: 10, overflow: "hidden", marginBottom: 24 }}>
            {/* Tabs */}
            <div style={{ display: "flex", borderBottom: `1px solid ${borderColor}` }}>
              {(["upload", "paste"] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  style={{
                    padding: "12px 20px", fontSize: 13.5, fontWeight: tab === t ? 600 : 400,
                    color: tab === t ? accentColor : "var(--text-secondary)",
                    background: "none", border: "none", cursor: "pointer",
                    borderBottom: tab === t ? `2px solid ${accentColor}` : "2px solid transparent",
                    marginBottom: -1, transition: "all 0.15s",
                  }}
                >
                  {t === "upload" ? (
                    <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12" /></svg>
                      上传表格
                    </span>
                  ) : (
                    <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" /></svg>
                      粘贴文本
                    </span>
                  )}
                </button>
              ))}
              <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "flex-end", paddingRight: 20 }}>
                <a
                  href="/询价选型模板.xls"
                  download
                  style={{ fontSize: 12, color: accentColor, textDecoration: "none", display: "flex", alignItems: "center", gap: 4 }}
                >
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3" /></svg>
                  下载模板
                </a>
              </div>
            </div>

            {/* Tab content */}
            <div style={{ padding: 24 }}>
              {tab === "upload" ? (
                <div
                  onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={handleDrop}
                  onClick={() => fileRef.current?.click()}
                  style={{
                    border: `2px dashed ${dragging ? accentColor : borderColor}`,
                    borderRadius: 8, padding: "48px 24px",
                    textAlign: "center", cursor: "pointer",
                    background: dragging ? "rgba(210,75,35,0.03)" : "transparent",
                    transition: "all 0.15s",
                  }}
                >
                  <div style={{ fontSize: 36, marginBottom: 12 }}>
                    <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke={dragging ? accentColor : "var(--text-muted)"} strokeWidth="1.5" strokeLinecap="round" style={{ margin: "0 auto" }}>
                      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
                      <path d="M14 2v6h6M12 18v-6M9 15l3-3 3 3" />
                    </svg>
                  </div>
                  <p style={{ fontSize: 15, fontWeight: 500, color: "var(--text-primary)", marginBottom: 6 }}>
                    将询价文件拖拽至此区域，或{" "}
                    <span style={{ color: accentColor }}>点击上传</span>
                  </p>
                  <p style={{ fontSize: 12.5, color: "var(--text-muted)" }}>
                    支持 .xlsx / .xls / .csv，最多 200 行 · 根据模板填写识别更精准
                  </p>
                  <input ref={fileRef} type="file" accept=".xlsx,.xls,.csv" style={{ display: "none" }} onChange={(e) => { const f = e.target.files?.[0]; if (f) processFile(f); e.target.value = ""; }} />
                </div>
              ) : (
                <div>
                  <p style={{ fontSize: 12.5, color: "var(--text-muted)", marginBottom: 10 }}>
                    每行一条需求，格式：品名, 品牌, 型号, 数量（逗号或 Tab 分隔，第一行可以是列标题）
                  </p>
                  <textarea
                    value={pasteText}
                    onChange={(e) => setPasteText(e.target.value)}
                    placeholder={"需求品名,需求品牌,需求型号,采购数量\nM8×30六角螺栓,东明,M8×30,500\nSKF深沟球轴承,SKF,6205-2RS,10"}
                    style={{
                      width: "100%", minHeight: 160, padding: "10px 12px",
                      border: `1px solid ${borderColor}`, borderRadius: 6,
                      fontSize: 13, fontFamily: "var(--mono)",
                      color: "var(--text-primary)", background: "transparent",
                      resize: "vertical", outline: "none", boxSizing: "border-box",
                    }}
                  />
                  <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 12 }}>
                    <button
                      onClick={handlePasteSubmit}
                      disabled={!pasteText.trim() || loading}
                      style={{
                        background: pasteText.trim() ? accentColor : "var(--border)",
                        color: pasteText.trim() ? "#fff" : "var(--text-muted)",
                        border: "none", borderRadius: 6, padding: "8px 24px",
                        fontSize: 13.5, fontWeight: 500, cursor: pasteText.trim() ? "pointer" : "not-allowed",
                      }}
                    >
                      开始匹配
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Loading state */}
        {loading && (
          <div style={{ background: "var(--surface)", border: `1px solid ${borderColor}`, borderRadius: 10, padding: "40px 24px", textAlign: "center", marginBottom: 24 }}>
            <div style={{ display: "flex", justifyContent: "center", gap: 6, marginBottom: 16 }}>
              {[0, 1, 2].map((i) => (
                <span key={i} className="thinking-dot" style={{ animationDelay: `${i * 0.2}s` }} />
              ))}
            </div>
            <p style={{ fontSize: 14, color: "var(--text-secondary)" }}>正在批量匹配产品，请稍候...</p>
          </div>
        )}

        {/* Error */}
        {error && (
          <div style={{ background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 8, padding: "12px 16px", marginBottom: 16, color: "#dc2626", fontSize: 13.5, display: "flex", alignItems: "center", gap: 8 }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="10" /><path d="M12 8v4M12 16h.01" /></svg>
            {error}
          </div>
        )}

        {/* Results */}
        {result && (
          <div style={{ marginBottom: 24 }}>
            {/* Summary bar */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, background: "var(--surface)", border: `1px solid ${borderColor}`, borderRadius: 8, padding: "8px 16px" }}>
                  <span style={{ fontSize: 22, fontWeight: 700, color: "var(--text-primary)", fontFamily: "var(--mono)" }}>{result.total}</span>
                  <span style={{ fontSize: 12, color: "var(--text-muted)" }}>总行数</span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 6, background: "var(--surface)", border: `1px solid ${borderColor}`, borderRadius: 8, padding: "8px 16px" }}>
                  <span style={{ fontSize: 22, fontWeight: 700, color: accentColor, fontFamily: "var(--mono)" }}>{result.matched}</span>
                  <span style={{ fontSize: 12, color: "var(--text-muted)" }}>已匹配</span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 6, background: "var(--surface)", border: `1px solid ${borderColor}`, borderRadius: 8, padding: "8px 16px" }}>
                  <span style={{ fontSize: 22, fontWeight: 700, color: "#6b7280", fontFamily: "var(--mono)" }}>{result.total - result.matched}</span>
                  <span style={{ fontSize: 12, color: "var(--text-muted)" }}>未匹配</span>
                </div>
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <button
                  onClick={() => { setResult(null); setError(""); }}
                  style={{ background: "none", border: `1px solid ${borderColor}`, borderRadius: 6, padding: "7px 16px", fontSize: 13, color: "var(--text-secondary)", cursor: "pointer" }}
                >
                  重新上传
                </button>
                <button
                  onClick={() => downloadCSV(result)}
                  style={{ background: accentColor, border: "none", borderRadius: 6, padding: "7px 16px", fontSize: 13, color: "#fff", fontWeight: 500, cursor: "pointer", display: "flex", alignItems: "center", gap: 6 }}
                >
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3" /></svg>
                  导出 CSV
                </button>
              </div>
            </div>

            {/* Results table */}
            <div style={{ background: "var(--surface)", border: `1px solid ${borderColor}`, borderRadius: 10, overflow: "hidden" }}>
              {/* Table header */}
              <div style={{ display: "grid", gridTemplateColumns: "50px 1fr 100px 130px 80px 60px", gap: 0, background: "#f8f9fb", borderBottom: `1px solid ${borderColor}`, padding: "10px 16px", fontSize: 12, color: "var(--text-muted)", fontWeight: 500 }}>
                <span>#</span>
                <span>需求品名 / 型号</span>
                <span>品牌</span>
                <span>采购数量</span>
                <span>匹配数</span>
                <span></span>
              </div>

              {result.rows.map((row) => {
                const expanded = expandedRows.has(row.index);
                return (
                  <div key={row.index} style={{ borderBottom: `1px solid ${borderColor}` }}>
                    {/* Row summary */}
                    <div
                      onClick={() => row.match_count > 0 && toggleRow(row.index)}
                      style={{
                        display: "grid", gridTemplateColumns: "50px 1fr 100px 130px 80px 60px",
                        gap: 0, padding: "11px 16px", alignItems: "center",
                        cursor: row.match_count > 0 ? "pointer" : "default",
                        transition: "background 0.1s",
                      }}
                      onMouseEnter={e => { if (row.match_count > 0) e.currentTarget.style.background = "#f8f9fb"; }}
                      onMouseLeave={e => { e.currentTarget.style.background = "transparent"; }}
                    >
                      <span style={{ fontSize: 12, color: "var(--text-muted)", fontFamily: "var(--mono)" }}>{row.index}</span>
                      <div style={{ minWidth: 0 }}>
                        <div style={{ fontSize: 13.5, color: "var(--text-primary)", fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {row.input.需求品名 || "—"}
                        </div>
                        {row.input.需求型号 && (
                          <div style={{ fontSize: 12, color: "var(--text-muted)", fontFamily: "var(--mono)", marginTop: 2 }}>
                            {row.input.需求型号}
                          </div>
                        )}
                      </div>
                      <span style={{ fontSize: 12.5, color: "var(--text-secondary)" }}>{row.input.需求品牌 || "—"}</span>
                      <span style={{ fontSize: 12.5, color: "var(--text-secondary)" }}>{row.input.采购数量 || "—"}</span>
                      <span>
                        {row.matched ? (
                          <span style={{ display: "inline-flex", alignItems: "center", gap: 4, background: "#dcfce7", color: "#15803d", borderRadius: 12, padding: "2px 8px", fontSize: 12, fontWeight: 500 }}>
                            {row.match_count} 个
                          </span>
                        ) : (
                          <span style={{ display: "inline-flex", alignItems: "center", gap: 4, background: "#f3f4f6", color: "#9ca3af", borderRadius: 12, padding: "2px 8px", fontSize: 12 }}>
                            未找到
                          </span>
                        )}
                      </span>
                      <span style={{ display: "flex", justifyContent: "center" }}>
                        {row.match_count > 0 && (
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="2" strokeLinecap="round" style={{ transform: expanded ? "rotate(180deg)" : "none", transition: "transform 0.2s" }}>
                            <path d="M6 9l6 6 6-6" />
                          </svg>
                        )}
                      </span>
                    </div>

                    {/* Expanded matches */}
                    {expanded && row.matches.length > 0 && (
                      <div style={{ background: "#f8f9fb", borderTop: `1px solid ${borderColor}`, padding: "8px 16px 12px 66px" }}>
                        <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 8, fontFamily: "var(--mono)" }}>
                          匹配结果（共 {row.match_count} 个，显示前 5）
                        </div>
                        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                          {row.matches.map((m) => (
                            <div key={m.item_code} style={{ display: "grid", gridTemplateColumns: "110px 1fr 100px 120px", gap: 8, background: "var(--surface)", border: `1px solid ${borderColor}`, borderRadius: 6, padding: "8px 12px", fontSize: 12.5 }}>
                              <span style={{ fontFamily: "var(--mono)", color: "var(--accent)", fontWeight: 500 }}>{m.item_code}</span>
                              <span style={{ color: "var(--text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{m.item_name}</span>
                              <span style={{ color: "var(--text-secondary)" }}>{m.brand_name || "—"}</span>
                              <span style={{ color: "var(--text-muted)", fontFamily: "var(--mono)", fontSize: 11.5, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{m.specification || m.mfg_sku || "—"}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* History */}
        {history.length > 0 && (
          <div style={{ marginTop: result ? 32 : 0 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="2" strokeLinecap="round">
                  <circle cx="12" cy="12" r="10" /><path d="M12 6v6l4 2" />
                </svg>
                <span style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)" }}>历史询价记录</span>
                <span style={{ fontSize: 12, color: "var(--text-muted)", background: "var(--surface)", border: `1px solid ${borderColor}`, borderRadius: 10, padding: "1px 8px", fontFamily: "var(--mono)" }}>{history.length}</span>
              </div>
              <button
                onClick={clearHistory}
                style={{ background: "none", border: "none", fontSize: 12, color: "var(--text-muted)", cursor: "pointer", padding: "4px 8px", borderRadius: 4 }}
                onMouseEnter={e => (e.currentTarget.style.color = "#dc2626")}
                onMouseLeave={e => (e.currentTarget.style.color = "var(--text-muted)")}
              >
                清空记录
              </button>
            </div>
            <div style={{ background: "var(--surface)", border: `1px solid ${borderColor}`, borderRadius: 10, overflow: "hidden" }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 70px 70px 70px 130px 110px", gap: 0, background: "#f8f9fb", borderBottom: `1px solid ${borderColor}`, padding: "9px 16px", fontSize: 12, color: "var(--text-muted)", fontWeight: 500 }}>
                <span>文件名称</span><span>总行数</span><span>已匹配</span><span>未匹配</span><span>时间</span><span>操作</span>
              </div>
              {history.map((h, hi) => (
                <div
                  key={h.id}
                  style={{
                    display: "grid", gridTemplateColumns: "1fr 70px 70px 70px 130px 110px",
                    gap: 0, padding: "10px 16px",
                    borderBottom: hi < history.length - 1 ? `1px solid ${borderColor}` : "none",
                    alignItems: "center", fontSize: 13,
                    transition: "background 0.1s",
                  }}
                  onMouseEnter={e => (e.currentTarget.style.background = "#f8f9fb")}
                  onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
                >
                  <div style={{ minWidth: 0, display: "flex", alignItems: "center", gap: 8 }}>
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="1.8" strokeLinecap="round" style={{ flexShrink: 0 }}>
                      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" /><path d="M14 2v6h6" />
                    </svg>
                    <span style={{ color: "var(--text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{h.filename}</span>
                  </div>
                  <span style={{ color: "var(--text-secondary)", fontFamily: "var(--mono)", fontSize: 12.5 }}>{h.total}</span>
                  <span style={{ color: "#15803d", fontFamily: "var(--mono)", fontSize: 12.5, fontWeight: 500 }}>{h.matched}</span>
                  <span style={{ color: "#9ca3af", fontFamily: "var(--mono)", fontSize: 12.5 }}>{h.total - h.matched}</span>
                  <span style={{ color: "var(--text-muted)", fontSize: 11.5 }}>{formatTime(h.time)}</span>
                  <div style={{ display: "flex", gap: 4 }}>
                    <button
                      onClick={() => { setResult(h.result); setError(""); window.scrollTo({ top: 0, behavior: "smooth" }); }}
                      style={{ background: "none", border: `1px solid ${borderColor}`, borderRadius: 4, padding: "3px 8px", fontSize: 11.5, color: "var(--text-secondary)", cursor: "pointer", whiteSpace: "nowrap" }}
                      onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = accentColor; (e.currentTarget as HTMLButtonElement).style.color = accentColor; }}
                      onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = borderColor; (e.currentTarget as HTMLButtonElement).style.color = "var(--text-secondary)"; }}
                    >查看</button>
                    <button
                      onClick={() => downloadCSV(h.result)}
                      style={{ background: "none", border: `1px solid ${borderColor}`, borderRadius: 4, padding: "3px 8px", fontSize: 11.5, color: accentColor, cursor: "pointer", whiteSpace: "nowrap" }}
                      onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = accentColor; (e.currentTarget as HTMLButtonElement).style.color = "#fff"; }}
                      onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = "none"; (e.currentTarget as HTMLButtonElement).style.color = accentColor; }}
                    >导出</button>
                    <button
                      onClick={() => deleteHistory(h.id)}
                      style={{ background: "none", border: "none", padding: "3px 5px", cursor: "pointer", color: "var(--text-muted)", borderRadius: 4, display: "flex", alignItems: "center" }}
                      title="删除"
                      onMouseEnter={e => (e.currentTarget.style.color = "#dc2626")}
                      onMouseLeave={e => (e.currentTarget.style.color = "var(--text-muted)")}
                    >
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                        <path d="M18 6L6 18M6 6l12 12" />
                      </svg>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
