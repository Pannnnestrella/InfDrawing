import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { createMessageId, type ChatMessage, type ChatMode } from "@/agent-panel/types";
import {
  createChatSession,
  loadChatHistory,
  makeSessionTitle,
  saveChatHistory,
  toPersistableMessages,
  type ChatSession,
} from "@/lib/chat-history";

export function useChatMessages() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const persistTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Keep a sync mirror so beginSession() + appendMessage() in the same tick work.
  const activeSessionIdRef = useRef<string | null>(null);

  useEffect(() => {
    const store = loadChatHistory();
    setSessions(store.sessions);
    setActiveSessionId(store.activeSessionId);
    activeSessionIdRef.current = store.activeSessionId;
    setHydrated(true);
  }, []);

  const schedulePersist = useCallback(
    (nextSessions: ChatSession[], nextActiveId: string | null) => {
      if (!hydrated) return;
      if (persistTimer.current) clearTimeout(persistTimer.current);
      persistTimer.current = setTimeout(() => {
        void (async () => {
          const sessionsToSave = await Promise.all(
            nextSessions.map(async (session) => ({
              ...session,
              messages: await toPersistableMessages(session.messages),
            })),
          );
          saveChatHistory({
            sessions: sessionsToSave,
            activeSessionId: nextActiveId,
          });
        })();
      }, 120);
    },
    [hydrated],
  );

  const activeSession = useMemo(
    () => sessions.find((session) => session.id === activeSessionId) ?? null,
    [sessions, activeSessionId],
  );

  const messages = activeSession?.messages ?? [];

  const beginSession = useCallback(
    (mode: ChatMode, userText: string) => {
      const session = createChatSession({
        mode,
        title: makeSessionTitle(mode, userText),
      });
      activeSessionIdRef.current = session.id;
      setActiveSessionId(session.id);
      setSessions((prev) => {
        const next = [session, ...prev];
        schedulePersist(next, session.id);
        return next;
      });
      return session.id;
    },
    [schedulePersist],
  );

  const selectSession = useCallback(
    (sessionId: string) => {
      activeSessionIdRef.current = sessionId;
      setActiveSessionId(sessionId);
      schedulePersist(sessions, sessionId);
    },
    [schedulePersist, sessions],
  );

  const startNewChat = useCallback(() => {
    activeSessionIdRef.current = null;
    setActiveSessionId(null);
    schedulePersist(sessions, null);
  }, [schedulePersist, sessions]);

  const clearAllSessions = useCallback(() => {
    activeSessionIdRef.current = null;
    setSessions([]);
    setActiveSessionId(null);
    schedulePersist([], null);
  }, [schedulePersist]);

  const appendMessage = useCallback(
    (entry: ChatMessage) => {
      setSessions((prev) => {
        const targetId = activeSessionIdRef.current;
        const index = prev.findIndex((session) => session.id === targetId);
        if (index < 0) {
          // No active session: create a fallback bucket so status/errors are not lost.
          const fallback = createChatSession({
            mode: entry.role === "user" ? entry.mode : "auto",
            title:
              entry.role === "user"
                ? makeSessionTitle(entry.mode, entry.text)
                : "未命名会话",
            messages: [entry],
          });
          activeSessionIdRef.current = fallback.id;
          setActiveSessionId(fallback.id);
          const next = [fallback, ...prev];
          schedulePersist(next, fallback.id);
          return next;
        }
        const current = prev[index];
        const updated: ChatSession = {
          ...current,
          updatedAt: Date.now(),
          messages: [...current.messages, entry],
        };
        const next = [...prev];
        next[index] = updated;
        // Keep most recently updated sessions near the top.
        next.sort((a, b) => b.updatedAt - a.updatedAt);
        schedulePersist(next, updated.id);
        return next;
      });
    },
    [schedulePersist],
  );

  const appendStatus = useCallback(
    (text: string) => {
      appendMessage({ id: createMessageId(), role: "assistant", kind: "status", text });
    },
    [appendMessage],
  );

  const appendError = useCallback(
    (text: string) => {
      appendMessage({ id: createMessageId(), role: "assistant", kind: "error", text });
    },
    [appendMessage],
  );

  const notifyReconnect = useCallback(
    (attempt: number) => {
      appendStatus(`连接断开，正在重连（第 ${attempt} 次）…`);
    },
    [appendStatus],
  );

  return {
    sessions,
    activeSessionId,
    activeSession,
    messages,
    hydrated,
    beginSession,
    selectSession,
    startNewChat,
    clearAllSessions,
    appendMessage,
    appendStatus,
    appendError,
    notifyReconnect,
  };
}
