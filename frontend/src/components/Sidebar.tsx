import { useState } from "react";
import { ChatSession } from "../types";

interface Props {
  sessions: ChatSession[];
  activeId: string;
  isOpen: boolean;
  onNewChat: () => void;
  onSelectChat: (id: string) => void;
  onDeleteChat: (id: string) => void;
  onClose: () => void;
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
  sessions,
  activeId,
  isOpen,
  onNewChat,
  onSelectChat,
  onDeleteChat,
  onClose,
}: Props) {
  const sorted = [...sessions].sort((a, b) => b.createdAt - a.createdAt);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);

  return (
    <>
      {/* Mobile overlay backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/40 z-40 md:hidden"
          onClick={onClose}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`
          fixed md:static inset-y-0 left-0 z-50
          w-64 bg-gray-900 text-white flex flex-col
          transform transition-transform duration-200 ease-in-out
          ${isOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"}
        `}
      >
        {/* Header */}
        <div className="p-3 border-b border-gray-700 shrink-0">
          <button
            onClick={onNewChat}
            className="w-full flex items-center gap-2 px-3 py-2.5 rounded-lg border border-gray-600 hover:bg-gray-700 transition-colors text-sm"
          >
            <svg
              className="w-4 h-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 4v16m8-8H4"
              />
            </svg>
            新建聊天
          </button>
        </div>

        {/* Chat list */}
        <div className="flex-1 overflow-y-auto py-2">
          {sorted.map((session) => (
            <div
              key={session.id}
              onClick={() => {
                onSelectChat(session.id);
                onClose();
              }}
              className={`
                group flex items-center gap-2 mx-2 px-3 py-2.5 rounded-lg cursor-pointer text-sm
                ${
                  session.id === activeId
                    ? "bg-gray-700 text-white"
                    : "text-gray-300 hover:bg-gray-800"
                }
              `}
            >
              <svg
                className="w-4 h-4 shrink-0 text-gray-500"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"
                />
              </svg>
              <div className="flex-1 min-w-0">
                <div className="truncate">{session.title}</div>
                <div className="text-xs text-gray-500">
                  {formatRelativeTime(session.createdAt)}
                </div>
              </div>
              {pendingDeleteId === session.id ? (
                <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
                  <button
                    onClick={() => {
                      onDeleteChat(session.id);
                      setPendingDeleteId(null);
                    }}
                    className="p-1 text-red-400 hover:text-red-300 transition-colors"
                    title="确认删除"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  </button>
                  <button
                    onClick={() => setPendingDeleteId(null)}
                    className="p-1 text-gray-400 hover:text-gray-200 transition-colors"
                    title="取消"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
              ) : (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setPendingDeleteId(session.id);
                  }}
                  className="opacity-0 group-hover:opacity-100 p-1 hover:text-red-400 transition-opacity shrink-0"
                  title="删除聊天"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>
              )}
            </div>
          ))}
          {sorted.length === 0 && (
            <div className="px-4 py-8 text-center text-gray-500 text-sm">
              暂无聊天记录
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-3 border-t border-gray-700 shrink-0">
          <div className="flex items-center gap-2 px-2 text-xs text-gray-500">
            <div className="w-6 h-6 bg-blue-600 rounded flex items-center justify-center shrink-0">
              <span className="text-white font-bold text-xs">M</span>
            </div>
            MRO 紧固件助手
          </div>
        </div>
      </aside>
    </>
  );
}
