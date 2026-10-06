"use client";

import { useState, useSyncExternalStore } from "react";

import {
  clearSessionApiKey,
  getSessionApiKey,
  setSessionApiKey,
  subscribeSessionApiKey,
} from "@/lib/api-client";

export function ApiKeyControl() {
  const [expanded, setExpanded] = useState(false);
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
    setExpanded(false);
  }

  return (
    <div className="relative">
      <button
        type="button"
        className="flex items-center gap-1.5 rounded-full border border-line bg-surface-2 px-2.5 py-1 text-[11px] text-muted transition-colors hover:bg-surface-3 hover:text-ink"
        title="设置 API Key"
        onClick={() => setExpanded((value) => !value)}
      >
        <span
          className={`h-1.5 w-1.5 rounded-full ${
            configured ? "bg-success" : "bg-muted"
          }`}
        />
        API Key
      </button>

      {expanded ? (
        <form
          className="absolute right-0 top-8 z-30 w-72 space-y-2 rounded-xl border border-line bg-surface-2 p-3 text-xs shadow-2xl"
          onSubmit={saveKey}
        >
          <label className="block font-medium text-ink" htmlFor="infd-api-key">
            API Key
          </label>
          <input
            id="infd-api-key"
            type="password"
            autoComplete="off"
            spellCheck={false}
            value={draft}
            placeholder={configured ? "已设置；输入新 Key 可替换" : "infd_…"}
            className="w-full rounded-lg border border-line bg-surface-1 px-2.5 py-2 text-ink outline-none focus:border-accent"
            onChange={(event) => setDraft(event.target.value)}
          />
          <p className="leading-relaxed text-muted">
            仅保存在当前浏览器会话的 sessionStorage 中。开发环境可留空。
          </p>
          <div className="flex justify-end gap-2">
            {configured ? (
              <button
                type="button"
                className="rounded-lg px-2.5 py-1.5 text-danger hover:bg-surface-3"
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
              className="rounded-lg bg-accent px-2.5 py-1.5 text-white disabled:cursor-not-allowed disabled:opacity-40"
            >
              保存
            </button>
          </div>
        </form>
      ) : null}
    </div>
  );
}
