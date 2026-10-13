"use client";

import { useState } from "react";

import { ImageIcon } from "@/components/icons";
import { Spinner } from "@/components/Spinner";
import type { EditSession } from "@/lib/controlled-edit-api";

interface UploadPanelProps {
  sessions: EditSession[];
  creating: boolean;
  disabled: boolean;
  compact?: boolean;
  onCreate: (file: File, title: string) => void;
  onCreateFromCanvas?: () => void;
  onOpen: (sessionId: string) => void;
  onRenameSession?: (sessionId: string, title: string) => Promise<void> | void;
  onDeleteSession?: (sessionId: string) => Promise<void> | void;
}

export function UploadPanel({
  sessions,
  creating,
  disabled,
  compact = false,
  onCreate,
  onCreateFromCanvas,
  onOpen,
  onRenameSession,
  onDeleteSession,
}: UploadPanelProps) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [dragging, setDragging] = useState(false);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);

  const pick = (candidate: File | undefined) => {
    if (!candidate || !candidate.type.startsWith("image/")) return;
    setFile(candidate);
    if (!title) setTitle(candidate.name.replace(/\.[^.]+$/, ""));
  };

  const startRename = (session: EditSession) => {
    setRenamingId(session.id);
    setDraftTitle(session.title);
  };

  const commitRename = async (sessionId: string) => {
    if (!onRenameSession) {
      setRenamingId(null);
      return;
    }
    const next = draftTitle.trim();
    if (!next) {
      setRenamingId(null);
      return;
    }
    setBusyId(sessionId);
    try {
      await onRenameSession(sessionId, next);
      setRenamingId(null);
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async (session: EditSession) => {
    if (!onDeleteSession) return;
    if (!window.confirm(`删除会话「${session.title}」及其全部版本？此操作不可撤销。`)) return;
    setBusyId(session.id);
    try {
      await onDeleteSession(session.id);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className={`mx-auto flex w-full flex-col gap-6 ${compact ? "max-w-none py-4" : "max-w-xl py-10"}`}>
      <div>
        <h1 className={compact ? "text-sm font-semibold" : "text-lg font-semibold"}>多轮可控编辑</h1>
        <p className="mt-1 text-xs text-muted">
          {compact
            ? "从画布选图开始，或打开已有会话。预览在窗口里；满意后点「导入画布」。"
            : "上传原图后，系统先解析场景实体。你可以锁定角色的脸、武器等元素，每轮修改都会用提示词约束、参考图锚定和 VLM 验收保护它们；所有版本记录在修改树中，随时回退或分支。"}
        </p>
      </div>

      {onCreateFromCanvas ? (
        <button
          type="button"
          disabled={creating || disabled}
          onClick={onCreateFromCanvas}
          className="rounded-lg bg-accent px-3 py-2 text-xs font-medium text-white hover:bg-accent-hover disabled:opacity-40"
        >
          {creating ? "解析场景中…" : "从选中的画布图开始"}
        </button>
      ) : null}

      <label
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          pick(event.dataTransfer.files[0]);
        }}
        className={`flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed px-6 py-10 text-xs transition-colors ${
          dragging ? "border-accent bg-accent/10" : "border-line-strong hover:border-accent"
        }`}
      >
        <ImageIcon size={28} className="text-muted" />
        {file ? (
          <span className="text-ink">{file.name}</span>
        ) : (
          <span className="text-muted">拖入图片，或点击选择（PNG / JPEG / WEBP）</span>
        )}
        <input
          type="file"
          accept="image/png,image/jpeg,image/webp"
          className="hidden"
          onChange={(event) => pick(event.target.files?.[0])}
        />
      </label>

      <div className="flex gap-2">
        <input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="会话标题"
          maxLength={120}
          className="flex-1 rounded-lg border border-line bg-surface-1 px-3 py-2 text-xs outline-none focus:border-accent"
        />
        <button
          type="button"
          disabled={!file || creating || disabled}
          onClick={() => file && onCreate(file, title.trim())}
          className="flex items-center gap-1.5 rounded-lg bg-accent px-4 py-2 text-xs font-medium text-white hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-40"
        >
          {creating ? <Spinner size={12} /> : null}
          {creating ? "解析场景中…" : "开始"}
        </button>
      </div>

      {sessions.length ? (
        <div>
          <h2 className="mb-2 text-xs font-semibold text-muted">历史会话</h2>
          <ul className="space-y-1">
            {sessions.map((session) => {
              const busy = busyId === session.id;
              const renaming = renamingId === session.id;
              return (
                <li
                  key={session.id}
                  className="flex items-center gap-1 rounded-lg px-2 py-1.5 hover:bg-surface-2"
                >
                  {renaming ? (
                    <input
                      autoFocus
                      value={draftTitle}
                      maxLength={120}
                      disabled={busy}
                      onChange={(event) => setDraftTitle(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") void commitRename(session.id);
                        if (event.key === "Escape") setRenamingId(null);
                      }}
                      onBlur={() => void commitRename(session.id)}
                      className="min-w-0 flex-1 rounded border border-accent bg-surface-1 px-2 py-1 text-xs outline-none"
                    />
                  ) : (
                    <button
                      type="button"
                      disabled={busy || disabled}
                      onClick={() => onOpen(session.id)}
                      className="min-w-0 flex-1 truncate text-left text-xs disabled:opacity-40"
                    >
                      {session.title}
                    </button>
                  )}
                  <span className="shrink-0 text-[10px] text-faint">
                    {new Date(session.updated_at).toLocaleString()}
                  </span>
                  {onRenameSession ? (
                    <button
                      type="button"
                      disabled={busy || disabled || renaming}
                      onClick={() => startRename(session)}
                      className="shrink-0 rounded px-1.5 py-0.5 text-[10px] text-muted hover:bg-surface-3 hover:text-ink disabled:opacity-40"
                    >
                      改名
                    </button>
                  ) : null}
                  {onDeleteSession ? (
                    <button
                      type="button"
                      disabled={busy || disabled}
                      onClick={() => void handleDelete(session)}
                      className="shrink-0 rounded px-1.5 py-0.5 text-[10px] text-danger hover:bg-danger/10 disabled:opacity-40"
                    >
                      {busy ? "…" : "删除"}
                    </button>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
