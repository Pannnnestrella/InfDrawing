import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  CHAT_HISTORY_STORAGE_KEY,
  MAX_CHAT_SESSIONS,
  createChatSession,
  loadChatHistory,
  makeSessionTitle,
  saveChatHistory,
  type ChatSession,
} from "./chat-history";

function makeSession(overrides: Partial<ChatSession> = {}): ChatSession {
  const now = Date.now();
  return {
    id: overrides.id ?? `sess-${Math.random().toString(36).slice(2)}`,
    title: overrides.title ?? "hello",
    mode: overrides.mode ?? "txt2img",
    createdAt: overrides.createdAt ?? now,
    updatedAt: overrides.updatedAt ?? now,
    messages: overrides.messages ?? [],
  };
}

describe("chat-history", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("builds a short title from user text", () => {
    expect(makeSessionTitle("txt2img", "  a cute cat  ")).toBe("a cute cat");
    expect(makeSessionTitle("auto", "")).toContain("新会话");
    expect(makeSessionTitle("inpaint", "x".repeat(40)).endsWith("…")).toBe(true);
  });

  it("persists and reloads sessions with active id", () => {
    const a = makeSession({ id: "a", updatedAt: 200 });
    const b = makeSession({ id: "b", updatedAt: 100 });
    saveChatHistory({ sessions: [a, b], activeSessionId: "b" });

    const loaded = loadChatHistory();
    expect(loaded.sessions.map((s) => s.id)).toEqual(["a", "b"]);
    expect(loaded.activeSessionId).toBe("b");
    expect(window.localStorage.getItem(CHAT_HISTORY_STORAGE_KEY)).toContain('"b"');
  });

  it("caps stored sessions at MAX_CHAT_SESSIONS", () => {
    const sessions = Array.from({ length: MAX_CHAT_SESSIONS + 5 }, (_, i) =>
      makeSession({ id: `s${i}`, updatedAt: i }),
    );
    saveChatHistory({ sessions, activeSessionId: "s0" });
    const loaded = loadChatHistory();
    expect(loaded.sessions).toHaveLength(MAX_CHAT_SESSIONS);
    expect(loaded.sessions[0]?.id).toBe(`s${MAX_CHAT_SESSIONS + 4}`);
  });

  it("falls back when activeSessionId is missing", () => {
    const session = makeSession({ id: "only" });
    saveChatHistory({ sessions: [session], activeSessionId: "gone" });
    expect(loadChatHistory().activeSessionId).toBe("only");
  });

  it("createChatSession assigns ids and timestamps", () => {
    const session = createChatSession({ mode: "image_edit", title: "edit me" });
    expect(session.id.startsWith("sess-")).toBe(true);
    expect(session.mode).toBe("image_edit");
    expect(session.messages).toEqual([]);
    expect(session.updatedAt).toBeGreaterThan(0);
  });
});
