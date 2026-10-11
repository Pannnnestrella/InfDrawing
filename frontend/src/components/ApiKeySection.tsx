"use client";

import { useState, useSyncExternalStore } from "react";

import {
  clearSessionApiKey,
  getSessionApiKey,
  setSessionApiKey,
  subscribeSessionApiKey,
} from "@/lib/api-client";

/** Session API Key form for the settings drawer. */
export function ApiKeySection() {
  const [draft, setDraft] = useState("");
  const configured = useSyncExternalStore(
    subscribeSessionApiKey,
    () => getSessionApiKey() !== null,
    () => false,
  );

  function saveKey(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!draft.trim()) return;
    setSessionApiKey(draft);
    setDraft("");
  }

  return (
    <form onSubmit={saveKey} className="space-y-2">
      <label className="block text-[11px] font-medium text-ink" htmlFor="infd-settings-api-key">
        InfDrawing API Key
      </label>
      <input
        id="infd-settings-api-key"
        type="password"
        autoComplete="off"
        spellCheck={false}
        value={draft}
        placeholder={configured ? "已设置；输入新 Key 可替换" : "infd_…"}
        className="w-full rounded-lg border border-line bg-surface-1 px-2.5 py-2 text-xs text-ink outline-none focus:border-accent"
        onChange={(event) => setDraft(event.target.value)}
      />
      <p className="leading-relaxed text-[11px] text-muted">
        仅保存在当前浏览器会话的 sessionStorage 中。开发环境可留空。
        {configured ? " · 当前会话已配置" : ""}
      </p>
      <div className="flex justify-end gap-2">
        {configured ? (
          <button
            type="button"
            className="rounded-lg px-2.5 py-1.5 text-[11px] text-danger hover:bg-surface-3"
            onClick={() => {
              clearSessionApiKey();
              setDraft("");
            }}
          >
            清除
          </button>
        ) : null}
        <button
          type="submit"
          disabled={!draft.trim()}
          className="rounded-lg bg-accent px-2.5 py-1.5 text-[11px] text-white disabled:cursor-not-allowed disabled:opacity-40"
        >
          保存
        </button>
      </div>
    </form>
  );
}
