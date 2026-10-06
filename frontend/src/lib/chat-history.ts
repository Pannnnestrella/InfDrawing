/** Local multi-session chat history for the AI panel. */

import type { ChatMessage, ChatMode } from "@/agent-panel/types";
import { createMessageId, MODE_LABELS } from "@/agent-panel/types";

export const CHAT_HISTORY_STORAGE_KEY = "infdrawing-chat-sessions-v1";
export const MAX_CHAT_SESSIONS = 30;
const TITLE_MAX_CHARS = 28;

export interface ChatSession {
  id: string;
  title: string;
  mode: ChatMode;
  createdAt: number;
  updatedAt: number;
  messages: ChatMessage[];
}

export interface ChatHistoryStore {
  sessions: ChatSession[];
  activeSessionId: string | null;
}

const EMPTY_STORE: ChatHistoryStore = {
  sessions: [],
  activeSessionId: null,
};

export function createSessionId(): string {
  return `sess-${createMessageId()}`;
}

export function makeSessionTitle(mode: ChatMode, userText: string): string {
  const trimmed = userText.trim().replace(/\s+/g, " ");
  if (!trimmed) {
    return `${MODE_LABELS[mode]} · 新会话`;
  }
  if (trimmed.length <= TITLE_MAX_CHARS) return trimmed;
  return `${trimmed.slice(0, TITLE_MAX_CHARS - 1)}…`;
}

export function loadChatHistory(): ChatHistoryStore {
  if (typeof window === "undefined") return EMPTY_STORE;
  try {
    const raw = window.localStorage.getItem(CHAT_HISTORY_STORAGE_KEY);
    if (!raw) return EMPTY_STORE;
    const parsed = JSON.parse(raw) as ChatHistoryStore;
    if (!parsed || !Array.isArray(parsed.sessions)) return EMPTY_STORE;
    const sessions = parsed.sessions
      .filter(isChatSession)
      .sort((a, b) => b.updatedAt - a.updatedAt)
      .slice(0, MAX_CHAT_SESSIONS);
    const activeSessionId =
      typeof parsed.activeSessionId === "string" &&
      sessions.some((s) => s.id === parsed.activeSessionId)
        ? parsed.activeSessionId
        : (sessions[0]?.id ?? null);
    return { sessions, activeSessionId };
  } catch {
    return EMPTY_STORE;
  }
}

export function saveChatHistory(store: ChatHistoryStore): void {
  if (typeof window === "undefined") return;
  const sessions = [...store.sessions]
    .sort((a, b) => b.updatedAt - a.updatedAt)
    .slice(0, MAX_CHAT_SESSIONS);
  const payload: ChatHistoryStore = {
    sessions,
    activeSessionId:
      store.activeSessionId && sessions.some((s) => s.id === store.activeSessionId)
        ? store.activeSessionId
        : (sessions[0]?.id ?? null),
  };
  window.localStorage.setItem(CHAT_HISTORY_STORAGE_KEY, JSON.stringify(payload));
}

export function createChatSession(input: {
  mode: ChatMode;
  title: string;
  messages?: ChatMessage[];
}): ChatSession {
  const now = Date.now();
  return {
    id: createSessionId(),
    title: input.title,
    mode: input.mode,
    createdAt: now,
    updatedAt: now,
    messages: input.messages ?? [],
  };
}

/** Prepare messages for durable storage (blob: → data:). */
export async function toPersistableMessages(
  messages: ChatMessage[],
): Promise<ChatMessage[]> {
  return Promise.all(
    messages.map(async (message) => {
      if (message.role !== "assistant" || message.kind !== "image") {
        return message;
      }
      if (!message.imageUrl.startsWith("blob:")) {
        return message;
      }
      try {
        const imageUrl = await blobUrlToDataUrl(message.imageUrl);
        return { ...message, imageUrl };
      } catch {
        return message;
      }
    }),
  );
}

export async function blobUrlToDataUrl(blobUrl: string): Promise<string> {
  const response = await fetch(blobUrl);
  if (!response.ok) {
    throw new Error(`failed to read blob: ${response.status}`);
  }
  const blob = await response.blob();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") {
        resolve(reader.result);
        return;
      }
      reject(new Error("failed to encode blob"));
    };
    reader.onerror = () => reject(new Error("failed to read blob"));
    reader.readAsDataURL(blob);
  });
}

export function formatSessionTime(ts: number): string {
  const date = new Date(ts);
  const now = new Date();
  const sameDay =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate();
  const hh = String(date.getHours()).padStart(2, "0");
  const mm = String(date.getMinutes()).padStart(2, "0");
  if (sameDay) return `${hh}:${mm}`;
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${month}-${day} ${hh}:${mm}`;
}

function isChatSession(value: unknown): value is ChatSession {
  if (!value || typeof value !== "object") return false;
  const session = value as ChatSession;
  return (
    typeof session.id === "string" &&
    typeof session.title === "string" &&
    typeof session.mode === "string" &&
    typeof session.createdAt === "number" &&
    typeof session.updatedAt === "number" &&
    Array.isArray(session.messages)
  );
}
