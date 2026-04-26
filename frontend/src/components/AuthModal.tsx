import { useState } from "react";
import { AuthUser } from "../types";
import { register, login } from "../services/auth";

interface Props {
  open: boolean;
  onClose?: () => void;          // optional — when undefined, modal cannot be dismissed
  onSuccess: (user: AuthUser) => void;
}

type Mode = "login" | "register";

export default function AuthModal({ open, onClose, onSuccess }: Props) {
  const [mode, setMode] = useState<Mode>("login");
  const [phone, setPhone] = useState("");
  const [nickname, setNickname] = useState("");
  const [inviteToken, setInviteToken] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  const submit = async () => {
    setError(null);
    if (!/^1[3-9]\d{9}$/.test(phone)) {
      setError("请输入有效的11位手机号");
      return;
    }
    if (mode === "register" && !inviteToken.trim()) {
      setError("请填写邀请码");
      return;
    }
    setLoading(true);
    try {
      const user = mode === "register"
        ? await register(phone, nickname.trim() || null, inviteToken.trim())
        : await login(phone);
      onSuccess(user);
      onClose?.();
    } catch (e: any) {
      setError(e?.message || "操作失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        position: "fixed", inset: 0, zIndex: 100,
        background: "rgba(0,0,0,0.55)",
        display: "flex", alignItems: "center", justifyContent: "center",
        padding: 16,
      }}
      onClick={onClose}     /* no-op when onClose is undefined (mandatory mode) */
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: "#fff", borderRadius: 12, width: "100%", maxWidth: 380,
          padding: "24px 24px 20px", boxShadow: "0 20px 60px rgba(0,0,0,0.3)",
        }}
      >
        <div style={{ display: "flex", marginBottom: 20, borderBottom: "1px solid #eef0f5" }}>
          {(["login", "register"] as Mode[]).map(m => (
            <button
              key={m}
              onClick={() => { setMode(m); setError(null); }}
              style={{
                flex: 1, padding: "8px 0",
                background: "none", border: "none",
                borderBottom: mode === m ? "2px solid var(--accent)" : "2px solid transparent",
                color: mode === m ? "#1a1f2e" : "#9aa3b8",
                fontSize: 14, fontWeight: mode === m ? 600 : 400,
                cursor: "pointer", marginBottom: -1,
              }}
            >
              {m === "login" ? "登录" : "注册"}
            </button>
          ))}
        </div>

        <div style={{ marginBottom: 12 }}>
          <label style={{ fontSize: 12, color: "#5b6478", marginBottom: 4, display: "block" }}>
            手机号
          </label>
          <input
            type="tel"
            value={phone}
            onChange={e => setPhone(e.target.value.replace(/\D/g, "").slice(0, 11))}
            placeholder="请输入11位手机号"
            style={{
              width: "100%", padding: "9px 12px",
              border: "1px solid #d8dde7", borderRadius: 6,
              fontSize: 14, outline: "none",
            }}
          />
        </div>

        {mode === "register" && (
          <>
            <div style={{ marginBottom: 12 }}>
              <label style={{ fontSize: 12, color: "#5b6478", marginBottom: 4, display: "block" }}>
                昵称（可选）
              </label>
              <input
                type="text"
                value={nickname}
                onChange={e => setNickname(e.target.value.slice(0, 20))}
                placeholder="不填则默认显示手机号末4位"
                style={{
                  width: "100%", padding: "9px 12px",
                  border: "1px solid #d8dde7", borderRadius: 6,
                  fontSize: 14, outline: "none",
                }}
              />
            </div>
            <div style={{ marginBottom: 12 }}>
              <label style={{ fontSize: 12, color: "#5b6478", marginBottom: 4, display: "block" }}>
                邀请码
              </label>
              <input
                type="text"
                value={inviteToken}
                onChange={e => setInviteToken(e.target.value)}
                placeholder="请向管理员索取"
                style={{
                  width: "100%", padding: "9px 12px",
                  border: "1px solid #d8dde7", borderRadius: 6,
                  fontSize: 14, outline: "none",
                }}
              />
            </div>
          </>
        )}

        {error && (
          <div style={{
            background: "#fef2f2", color: "#dc2626", padding: "8px 12px",
            borderRadius: 6, fontSize: 12, marginBottom: 12,
          }}>
            {error}
          </div>
        )}

        <button
          onClick={submit}
          disabled={loading}
          style={{
            width: "100%", padding: "10px 0",
            background: loading ? "#9aa3b8" : "var(--accent)",
            color: "#fff", border: "none", borderRadius: 6,
            fontSize: 14, fontWeight: 500,
            cursor: loading ? "not-allowed" : "pointer",
          }}
        >
          {loading ? "处理中…" : mode === "login" ? "登录" : "注册并登录"}
        </button>

        <div style={{ fontSize: 11, color: "#9aa3b8", marginTop: 12, textAlign: "center" }}>
          登录后将记录您的对话历史与采购偏好，跨设备同步
        </div>
      </div>
    </div>
  );
}
