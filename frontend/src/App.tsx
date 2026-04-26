import { useState, useEffect, useCallback, useRef } from "react";
import { ChatSession, ChatMessage, AuthUser } from "./types";
import ChatWindow from "./components/ChatWindow";
import Sidebar from "./components/Sidebar";
import InquiryPage from "./components/InquiryPage";
import AuthModal from "./components/AuthModal";
import { fetchMe, getStoredUser, logout as doLogout } from "./services/auth";

const STORAGE_KEY = "mro-chat-sessions";
const MAX_SESSIONS = 50;
const SAVE_DEBOUNCE_MS = 1000;

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

function loadSessions(): ChatSession[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed: ChatSession[] = JSON.parse(raw);
      return parsed.map((s) => ({
        ...s,
        messages: s.messages.map((m) => ({ ...m, isStreaming: false })),
      }));
    }
  } catch {
    // ignore corrupt data
  }
  return [];
}

function saveSessions(sessions: ChatSession[]) {
  const toSave = [...sessions]
    .sort((a, b) => b.createdAt - a.createdAt)
    .slice(0, MAX_SESSIONS)
    .map((s) => ({
      ...s,
      messages: s.messages.map(({ isStreaming, ...rest }) => rest),
    }));
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(toSave));
  } catch {
    // quota exceeded — silently ignore
  }
}

function deriveTitle(messages: ChatMessage[]): string {
  const firstUserMsg = messages.find((m) => m.role === "user");
  if (!firstUserMsg) return "新对话";
  const text = firstUserMsg.content.trim();
  return text.length > 20 ? text.slice(0, 20) + "…" : text;
}

export default function App() {
  const [sessions, setSessions] = useState<ChatSession[]>(() => {
    const loaded = loadSessions();
    return loaded.length > 0 ? loaded : [createSession()];
  });
  const [activeId, setActiveId] = useState<string>(
    () => sessions[0]?.id ?? ""
  );
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [activeView, setActiveView] = useState<"chat" | "inquiry">("chat");

  const [user, setUser] = useState<AuthUser | null>(() => getStoredUser());

  // Validate token against server on mount; clears stale tokens automatically
  useEffect(() => {
    if (user) {
      fetchMe().then(u => setUser(u)).catch(() => setUser(null));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Global 401 listener — any auth-failed API call kicks user back to login
  useEffect(() => {
    const onUnauthorized = () => {
      doLogout();
      setUser(null);
    };
    window.addEventListener("mro:unauthorized", onUnauthorized);
    return () => window.removeEventListener("mro:unauthorized", onUnauthorized);
  }, []);

  const handleLogout = useCallback(() => {
    doLogout();
    setUser(null);
  }, []);

  // Debounced localStorage persistence
  const saveTimerRef = useRef<ReturnType<typeof setTimeout>>();
  const sessionsRef = useRef(sessions);
  sessionsRef.current = sessions;

  useEffect(() => {
    clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => {
      saveSessions(sessionsRef.current);
    }, SAVE_DEBOUNCE_MS);
    return () => clearTimeout(saveTimerRef.current);
  }, [sessions]);

  // Also save immediately on page unload
  useEffect(() => {
    const handleBeforeUnload = () => {
      saveSessions(sessionsRef.current);
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, []);

  const activeSession = sessions.find((s) => s.id === activeId);

  const handleMessagesChange = useCallback(
    (msgs: ChatMessage[]) => {
      setSessions((prev) =>
        prev.map((s) =>
          s.id === activeId
            ? { ...s, messages: msgs, title: deriveTitle(msgs) }
            : s
        )
      );
    },
    [activeId]
  );

  const handleNewChat = useCallback(() => {
    // Reuse existing empty session if one exists
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
