import { useState, useRef } from "react";
import { ChatSession, AuthUser } from "../types";
import { authHeader } from "../services/auth";

interface Props {
  sessions: ChatSession[];
  activeId: string;
  isOpen: boolean;
  activeView: "chat" | "inquiry";
  user: AuthUser | null;
  onNewChat: () => void;
  onSelectChat: (id: string) => void;
  onDeleteChat: (id: string) => void;
  onClose: () => void;
  onNavigate: (view: "chat" | "inquiry") => void;
  onLogout: () => void;
}

function formatRelativeTime(timestamp: number): string {
  const diff = Date.now() - timestamp;
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes}分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}小时前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}天前`;
  const months = Math.floor(days / 30);
  return `${months}个月前`;
}

export default function Sidebar({
  sessions, activeId, isOpen, activeView, user,
  onNewChat, onSelectChat, onDeleteChat, onClose, onNavigate, onLogout,
}: Props) {
  const sorted = [...sessions].sort((a, b) => b.createdAt - a.createdAt);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [importStatus, setImportStatus] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleImportClick = () => {
    setImportStatus(null);
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";

    setImportStatus("正在导入...");
    const sessionId = localStorage.getItem("mro_session_id") || "unknown";

    const form = new FormData();
    form.append("file", file);
    form.append("session_id", sessionId);

    try {
      const res = await fetch("/api/profile/import", { method: "POST", body: form, headers: authHeader() });
      if (res.status === 401) {
        window.dispatchEvent(new Event("mro:unauthorized"));
        setImportStatus("✗ 登录已失效，请重新登录");
        return;
      }
      const data = await res.json();
      if (res.ok) {
        setImportStatus(`✓ 已导入 ${data.total_records} 条记录`);
      } else {
        setImportStatus(`✗ ${data.detail || "导入失败"}`);
      }
    } catch {
      setImportStatus("✗ 网络错误，请重试");
    }

    setTimeout(() => setImportStatus(null), 4000);
  };

  return (
    <>
      {isOpen && (
        <div
          className="fixed inset-0 z-40 md:hidden"
          style={{ background: "rgba(0,0,0,0.5)" }}
          onClick={onClose}
        />
      )}

      <aside
        style={{ background: "var(--sidebar-bg)", borderRight: "1px solid var(--sidebar-border)", width: 240 }}
        className={`
          fixed md:static inset-y-0 left-0 z-50 flex flex-col shrink-0
          transform transition-transform duration-200 ease-in-out
          ${isOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"}
        `}
      >
        {/* Brand */}
        <div
          style={{ borderBottom: "1px solid var(--sidebar-border)", padding: "16px 16px 14px" }}
          className="shrink-0"
        >
          <div className="flex items-center gap-2.5 mb-3">
            <div
              style={{
                width: 28, height: 28,
                background: "var(--accent)",
                borderRadius: 6,
                display: "flex", alignItems: "center", justifyContent: "center",
                flexShrink: 0,
              }}
            >
              <span style={{ color: "#fff", fontWeight: 700, fontSize: 13, fontFamily: "var(--mono)" }}>M</span>
            </div>
            <div>
              <div style={{ color: "#fff", fontWeight: 600, fontSize: 13, lineHeight: 1.2 }}>MRO 助手</div>
              <div style={{ color: "var(--text-muted)", fontSize: 11, marginTop: 1 }}>工业品智能采购</div>
            </div>
          </div>

          <button
            onClick={onNewChat}
            style={{
              width: "100%",
              display: "flex", alignItems: "center", gap: 6,
              padding: "7px 12px",
              border: "1px solid #2a2f42",
              borderRadius: 6,
              background: "transparent",
              color: "#9aa3b8",
              fontSize: 13,
              cursor: "pointer",
              transition: "all 0.15s",
            }}
            onMouseEnter={e => {
              (e.currentTarget as HTMLButtonElement).style.background = "var(--sidebar-hover)";
              (e.currentTarget as HTMLButtonElement).style.color = "#fff";
            }}
            onMouseLeave={e => {
              (e.currentTarget as HTMLButtonElement).style.background = "transparent";
              (e.currentTarget as HTMLButtonElement).style.color = "#9aa3b8";
            }}
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <path d="M12 5v14M5 12h14" />
            </svg>
            新建对话
          </button>
        </div>

        {/* Nav */}
        <div style={{ padding: "8px 8px", borderBottom: "1px solid var(--sidebar-border)" }}>
          {[
            { view: "chat" as const, label: "智能对话", icon: <path strokeLinecap="round" strokeLinejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" /> },
            { view: "inquiry" as const, label: "批量询价", icon: <path strokeLinecap="round" strokeLinejoin="round" d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /> },
          ].map(({ view, label, icon }) => {
            const active = activeView === view;
            return (
              <button
                key={view}
                onClick={() => { onNavigate(view); onClose(); }}
                style={{
                  width: "100%",
                  display: "flex", alignItems: "center", gap: 8,
                  padding: "7px 10px",
                  borderRadius: 6,
                  background: active ? "var(--sidebar-active)" : "transparent",
                  border: "none",
                  borderLeft: `2px solid ${active ? "var(--accent)" : "transparent"}`,
                  color: active ? "#fff" : "#8890a4",
                  fontSize: 13,
                  cursor: "pointer",
                  transition: "all 0.12s",
                  marginBottom: 2,
                  textAlign: "left",
                }}
                onMouseEnter={e => { if (!active) (e.currentTarget as HTMLButtonElement).style.background = "var(--sidebar-hover)"; }}
                onMouseLeave={e => { if (!active) (e.currentTarget as HTMLButtonElement).style.background = "transparent"; }}
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke={active ? "var(--accent)" : "#4a5068"} strokeWidth="1.8" style={{ flexShrink: 0 }}>
                  {icon}
                </svg>
                {label}
              </button>
            );
          })}
        </div>

        {/* Session list */}
        <div className="flex-1 overflow-y-auto" style={{ padding: "8px 8px" }}>
          {sorted.length === 0 && (
            <div style={{ color: "var(--text-muted)", fontSize: 12, textAlign: "center", padding: "24px 0" }}>
              暂无对话记录
            </div>
          )}
          {sorted.map((session) => {
            const isActive = session.id === activeId;
            return (
              <div
                key={session.id}
                onClick={() => { onSelectChat(session.id); onClose(); }}
                style={{
                  display: "flex", alignItems: "center", gap: 8,
                  padding: "8px 10px",
                  borderRadius: 6,
                  cursor: "pointer",
                  marginBottom: 2,
                  borderLeft: isActive ? "2px solid var(--accent)" : "2px solid transparent",
                  background: isActive ? "var(--sidebar-active)" : "transparent",
                  transition: "all 0.12s",
                }}
                className="group"
                onMouseEnter={e => {
                  if (!isActive) (e.currentTarget as HTMLDivElement).style.background = "var(--sidebar-hover)";
                }}
                onMouseLeave={e => {
                  if (!isActive) (e.currentTarget as HTMLDivElement).style.background = "transparent";
                }}
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke={isActive ? "var(--accent)" : "#4a5068"} strokeWidth="1.8" style={{ flexShrink: 0, marginTop: 1 }}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                </svg>

                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    color: isActive ? "#fff" : "#8890a4",
                    fontSize: 12.5,
                    fontWeight: isActive ? 500 : 400,
                    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                  }}>
                    {session.title}
                  </div>
                  <div style={{ color: "#4a5068", fontSize: 11, marginTop: 1 }}>
                    {formatRelativeTime(session.createdAt)}
                  </div>
                </div>

                {pendingDeleteId === session.id ? (
                  <div
                    style={{ display: "flex", gap: 2, flexShrink: 0 }}
                    onClick={e => e.stopPropagation()}
                  >
                    <button
                      onClick={() => { onDeleteChat(session.id); setPendingDeleteId(null); }}
                      style={{ background: "none", border: "none", color: "#f87171", cursor: "pointer", padding: 3, borderRadius: 3 }}
                      title="确认删除"
                    >
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                        <path d="M5 13l4 4L19 7" />
                      </svg>
                    </button>
                    <button
                      onClick={() => setPendingDeleteId(null)}
                      style={{ background: "none", border: "none", color: "#6b7280", cursor: "pointer", padding: 3, borderRadius: 3 }}
                      title="取消"
                    >
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                        <path d="M18 6L6 18M6 6l12 12" />
                      </svg>
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={e => { e.stopPropagation(); setPendingDeleteId(session.id); }}
                    style={{
                      background: "none", border: "none", color: "#4a5068", cursor: "pointer",
                      padding: 3, borderRadius: 3, flexShrink: 0,
                    }}
                    className="opacity-0 group-hover:opacity-100 transition-opacity duration-150"
                    title="删除对话"
                  >
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                )}
              </div>
            );
          })}
        </div>

        {/* Footer */}
        <div style={{ borderTop: "1px solid var(--sidebar-border)", padding: "12px 16px" }} className="shrink-0">
          {/* User section — always present once logged in (mandatory login means user is never null here in practice) */}
          {user && (
            <div style={{
              display: "flex", alignItems: "center", gap: 8,
              padding: "8px 10px", marginBottom: 10,
              background: "var(--sidebar-active)", borderRadius: 6,
            }}>
              <div style={{
                width: 24, height: 24, borderRadius: "50%",
                background: "var(--accent)", color: "#fff",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 11, fontWeight: 600, flexShrink: 0,
              }}>
                {(user.nickname || user.phone.slice(-4))[0]?.toUpperCase() || "U"}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ color: "#fff", fontSize: 12, fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {user.nickname || `用户${user.phone.slice(-4)}`}
                </div>
                <div style={{ color: "#5b6478", fontSize: 10, fontFamily: "var(--mono)" }}>
                  {user.phone.slice(0, 3)}****{user.phone.slice(-4)}
                </div>
              </div>
              <button
                onClick={onLogout}
                title="退出登录"
                style={{ background: "none", border: "none", color: "#5b6478", cursor: "pointer", padding: 4, borderRadius: 3, flexShrink: 0 }}
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                </svg>
              </button>
            </div>
          )}

          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx,.xls,.csv"
            style={{ display: "none" }}
            onChange={handleFileChange}
          />
          <button
            onClick={handleImportClick}
            style={{
              width: "100%", background: "none", border: "1px solid var(--sidebar-border)",
              borderRadius: 6, padding: "6px 10px", cursor: "pointer",
              color: "var(--text-secondary)", fontSize: 11,
              display: "flex", alignItems: "center", gap: 6, marginBottom: 8,
            }}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
            </svg>
            导入采购历史
          </button>
          {importStatus && (
            <div style={{ fontSize: 10, color: importStatus.startsWith("✓") ? "#48bb78" : "#e53e3e", marginBottom: 6 }}>
              {importStatus}
            </div>
          )}
          <a
            href="/manual.pdf"
            target="_blank"
            rel="noopener noreferrer"
            style={{
              width: "100%", background: "none", border: "1px solid var(--sidebar-border)",
              borderRadius: 6, padding: "6px 10px", cursor: "pointer",
              color: "var(--text-secondary)", fontSize: 11,
              display: "flex", alignItems: "center", gap: 6, marginBottom: 8,
              textDecoration: "none", boxSizing: "border-box",
            }}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827v.5M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9 5h.01" />
            </svg>
            使用帮助
          </a>
          <div style={{ color: "#3a3f52", fontSize: 11, display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontFamily: "var(--mono)" }}>v1.0</span>
            <span style={{ color: "#2a2f40" }}>·</span>
            <span>200万+ SKU</span>
          </div>
        </div>
      </aside>
    </>
  );
}
