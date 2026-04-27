import { useState, useEffect, useCallback } from "react";
import { ChatSession, ChatMessage, AuthUser } from "./types";
import ChatWindow from "./components/ChatWindow";
import Sidebar from "./components/Sidebar";
import InquiryPage from "./components/InquiryPage";
import AuthModal from "./components/AuthModal";
import { fetchMe, getStoredUser, logout as doLogout } from "./services/auth";
import {
  listSessions,
  getSession,
  deleteSession as apiDeleteSession,
  summaryToSession,
  detailToSession,
} from "./services/chatHistory";

const LEGACY_STORAGE_KEY = "mro-chat-sessions";

function generateId() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2);
}

function createSession(): ChatSession {
  return {
    id: generateId(),
    title: "新对话",
    messages: [],
    createdAt: Date.now(),
  };
}

export default function App() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeId, setActiveId] = useState<string>("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [activeView, setActiveView] = useState<"chat" | "inquiry">("chat");

  const [user, setUser] = useState<AuthUser | null>(() => getStoredUser());

  // Validate token + drop any legacy localStorage history (server-side now)
  useEffect(() => {
    localStorage.removeItem(LEGACY_STORAGE_KEY);
    if (user) {
      fetchMe().then(u => setUser(u)).catch(() => setUser(null));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 401 → logout
  useEffect(() => {
    const onUnauthorized = () => {
      doLogout();
      setUser(null);
      setSessions([]);
      setActiveId("");
    };
    window.addEventListener("mro:unauthorized", onUnauthorized);
    return () => window.removeEventListener("mro:unauthorized", onUnauthorized);
  }, []);

  // Load sessions from server when user logs in
  useEffect(() => {
    if (!user) {
      setSessions([]);
      setActiveId("");
      return;
    }
    listSessions()
      .then(summaries => {
        if (summaries.length === 0) {
          const blank = createSession();
          setSessions([blank]);
          setActiveId(blank.id);
        } else {
          const sess = summaries.map(summaryToSession);
          setSessions(sess);
          setActiveId(sess[0].id);
        }
      })
      .catch(() => {
        // On error, fall back to one fresh session so user can still chat
        const blank = createSession();
        setSessions([blank]);
        setActiveId(blank.id);
      });
  }, [user]);

  const handleLogout = useCallback(() => {
    doLogout();
    setUser(null);
  }, []);

  const activeSession = sessions.find((s) => s.id === activeId);

  // Lazy-load messages on demand (when a session is selected and has no messages yet)
  useEffect(() => {
    if (!activeSession || activeSession.messages.length > 0) return;
    // Newly-created blank session (never sent to server) has createdAt very recent — skip fetch
    const isNewBlank = activeSession.title === "新对话" && Date.now() - activeSession.createdAt < 5000;
    if (isNewBlank) return;
    getSession(activeSession.id)
      .then(detail => {
        if (!detail) return;
        const full = detailToSession(detail);
        setSessions(prev => prev.map(s => (s.id === full.id ? full : s)));
      })
      .catch(() => { /* ignore — leave empty */ });
  }, [activeId]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleMessagesChange = useCallback(
    (msgs: ChatMessage[]) => {
      setSessions((prev) =>
        prev.map((s) =>
          s.id === activeId
            ? {
                ...s,
                messages: msgs,
                title: s.title === "新对话" && msgs.find(m => m.role === "user")
                  ? deriveTitle(msgs)
                  : s.title,
              }
            : s
        )
      );
    },
    [activeId]
  );

  const handleNewChat = useCallback(() => {
    setSessions((prev) => {
      const empty = prev.find((s) => s.messages.length === 0);
      if (empty) {
        setActiveId(empty.id);
        return prev;
      }
      const newSession = createSession();
      setActiveId(newSession.id);
      return [newSession, ...prev];
    });
  }, []);

  const handleSelectChat = useCallback((id: string) => {
    setActiveId(id);
  }, []);

  const handleDeleteChat = useCallback(
    (id: string) => {
      // Optimistically remove; reconcile if API call fails
      setSessions((prev) => {
        const next = prev.filter((s) => s.id !== id);
        if (next.length === 0) {
          const newSession = createSession();
          next.push(newSession);
        }
        if (id === activeId) {
          const sorted = [...next].sort((a, b) => b.createdAt - a.createdAt);
          setActiveId(sorted[0].id);
        }
        return next;
      });
      // Fire-and-forget delete on server (only matters if it was persisted)
      apiDeleteSession(id).catch(() => { /* ignore */ });
    },
    [activeId]
  );

  const handleToggleSidebar = useCallback(() => {
    setSidebarOpen((prev) => !prev);
  }, []);

  const handleCloseSidebar = useCallback(() => {
    setSidebarOpen(false);
  }, []);

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar
        sessions={sessions}
        activeId={activeId}
        isOpen={sidebarOpen}
        activeView={activeView}
        user={user}
        onNewChat={handleNewChat}
        onSelectChat={(id) => { handleSelectChat(id); setActiveView("chat"); }}
        onDeleteChat={handleDeleteChat}
        onClose={handleCloseSidebar}
        onNavigate={setActiveView}
        onLogout={handleLogout}
      />
      {activeView === "inquiry" ? (
        <InquiryPage onToggleSidebar={handleToggleSidebar} />
      ) : activeSession && (
        <ChatWindow
          key={activeSession.id}
          sessionId={activeSession.id}
          messages={activeSession.messages}
          onMessagesChange={handleMessagesChange}
          onToggleSidebar={handleToggleSidebar}
        />
      )}

      {/* Mandatory login modal — onClose omitted so it cannot be dismissed */}
      <AuthModal
        open={!user}
        onSuccess={(u) => setUser(u)}
      />
    </div>
  );
}

function deriveTitle(messages: ChatMessage[]): string {
  const firstUserMsg = messages.find((m) => m.role === "user");
  if (!firstUserMsg) return "新对话";
  const text = firstUserMsg.content.trim();
  return text.length > 20 ? text.slice(0, 20) + "…" : text;
}
