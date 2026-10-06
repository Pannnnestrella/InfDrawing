"use client";

import { MODE_LABELS } from "@/agent-panel/types";
import { formatSessionTime, type ChatSession } from "@/lib/chat-history";

interface SessionSwitcherProps {
  sessions: ChatSession[];
  activeSessionId: string | null;
  busy: boolean;
  onSelect: (sessionId: string) => void;
  onNewChat: () => void;
  onClearAll: () => void;
}

export function SessionSwitcher({
  sessions,
  activeSessionId,
  busy,
  onSelect,
  onNewChat,
  onClearAll,
}: SessionSwitcherProps) {
  return (
    <div className="shrink-0 space-y-2 border-b border-line px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[11px] font-medium text-muted">会话历史</p>
        <div className="flex items-center gap-1">
          <button
            type="button"
            disabled={busy}
            className="rounded-md px-2 py-1 text-[11px] text-ink transition-colors hover:bg-surface-2 disabled:opacity-40"
            onClick={onNewChat}
          >
            新对话
          </button>
          <button
            type="button"
            disabled={busy || sessions.length === 0}
            className="rounded-md px-2 py-1 text-[11px] text-muted transition-colors hover:bg-surface-2 hover:text-danger disabled:opacity-40"
            onClick={() => {
              if (window.confirm("清空全部会话历史？此操作不可恢复。")) {
                onClearAll();
              }
            }}
          >
            清空
          </button>
        </div>
      </div>

      {sessions.length === 0 ? (
        <p className="px-0.5 text-[11px] text-faint">发送请求后会在这里留下独立会话</p>
      ) : (
        <div className="flex max-h-28 flex-col gap-1 overflow-y-auto panel-scroll">
          {sessions.map((session) => {
            const active = session.id === activeSessionId;
            return (
              <button
                key={session.id}
                type="button"
                disabled={busy && !active}
                title={session.title}
                className={`rounded-lg px-2.5 py-1.5 text-left transition-colors disabled:opacity-50 ${
                  active
                    ? "bg-surface-3 text-ink"
                    : "text-muted hover:bg-surface-2 hover:text-ink"
                }`}
                onClick={() => onSelect(session.id)}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-[11px] font-medium">{session.title}</span>
                  <span className="shrink-0 text-[10px] text-faint">
                    {formatSessionTime(session.updatedAt)}
                  </span>
                </div>
                <p className="mt-0.5 text-[10px] text-faint">
                  {MODE_LABELS[session.mode]} · {session.messages.length} 条
                </p>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
