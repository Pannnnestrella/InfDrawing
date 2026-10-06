"use client";

import { useState } from "react";

import { SendIcon } from "@/components/icons";
import { Spinner } from "@/components/Spinner";
import type { LockConflictEntity, SceneEntity } from "@/lib/controlled-edit-api";

import {
  type ImageModelOption,
  type ImageProviderOption,
  type PromptStyleOption,
  promptStyleLabel,
} from "./studio-turn-options";

interface EditComposerProps {
  selectedTargets: SceneEntity[];
  disabled: boolean;
  disabledReason: string | null;
  submitting: boolean;
  conflict: { instruction: string; entities: LockConflictEntity[] } | null;
  promptStyle: PromptStyleOption;
  imageProvider: ImageProviderOption;
  imageOptions: ImageModelOption[];
  onPromptStyleChange: (style: PromptStyleOption) => void;
  onImageProviderChange: (provider: ImageProviderOption) => void;
  onSubmit: (instruction: string) => Promise<boolean>;
  onUnlockAndRetry: () => void;
  onDismissConflict: () => void;
}

export function EditComposer({
  disabled,
  disabledReason,
  submitting,
  selectedTargets,
  conflict,
  promptStyle,
  imageProvider,
  imageOptions,
  onPromptStyleChange,
  onImageProviderChange,
  onSubmit,
  onUnlockAndRetry,
  onDismissConflict,
}: EditComposerProps) {
  const [text, setText] = useState("");
  const blocked = disabled || submitting;

  const submit = async () => {
    const instruction = text.trim();
    if (!instruction || blocked) return;
    if (await onSubmit(instruction)) setText("");
  };

  return (
    <section className="space-y-2">
      <h2 className="text-xs font-semibold tracking-wide">编辑指令</h2>
      <div className="grid grid-cols-2 gap-2">
        <label className="space-y-1 text-[10px] text-faint">
          <span>提示词策略</span>
          <select
            value={promptStyle}
            disabled={blocked}
            onChange={(event) => onPromptStyleChange(event.target.value as PromptStyleOption)}
            className="w-full rounded-md border border-line bg-surface-1 px-2 py-1.5 text-xs text-ink outline-none focus:border-accent disabled:opacity-50"
          >
            <option value="preserve">{promptStyleLabel("preserve")}</option>
            <option value="target_only">{promptStyleLabel("target_only")}</option>
          </select>
        </label>
        <label className="space-y-1 text-[10px] text-faint">
          <span>生图模型</span>
          <select
            value={imageProvider}
            disabled={blocked || imageOptions.length === 0}
            onChange={(event) =>
              onImageProviderChange(event.target.value as ImageProviderOption)
            }
            className="w-full rounded-md border border-line bg-surface-1 px-2 py-1.5 text-xs text-ink outline-none focus:border-accent disabled:opacity-50"
          >
            {imageOptions.length === 0 ? (
              <option value={imageProvider}>暂无可用模型</option>
            ) : (
              imageOptions.map((option) => (
                <option key={option.provider} value={option.provider}>
                  {option.label}
                </option>
              ))
            )}
          </select>
        </label>
      </div>
      <textarea
        value={text}
        onChange={(event) => setText(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
            event.preventDefault();
            void submit();
          }
        }}
        rows={3}
        disabled={blocked}
        placeholder={disabledReason ?? "例如：给角色戴一顶 Halloween 女巫帽（Ctrl+Enter 发送）"}
        className="w-full resize-none rounded-lg border border-line bg-surface-1 px-3 py-2 text-xs outline-none placeholder:text-faint focus:border-accent disabled:opacity-50"
      />
      <div className="flex items-center justify-between">
        <span className="text-[10px] text-faint">
          {selectedTargets.length
            ? `本轮目标：${selectedTargets.map((e) => e.name).join("、")}`
            : "点选实体作为本轮目标，或只写指令"}
        </span>
        <button
          type="button"
          onClick={() => void submit()}
          disabled={blocked || !text.trim()}
          className="flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-40"
        >
          {submitting ? <Spinner size={12} /> : <SendIcon size={13} />}
          {submitting ? "解析指令…" : "生成"}
        </button>
      </div>

      {conflict ? (
        <div className="space-y-2 rounded-lg border border-warning/40 bg-warning/10 p-2.5 text-[11px]">
          <p className="text-warning">
            指令「{conflict.instruction}」会修改已锁定的实体：
            {conflict.entities.map((e) => e.name).join("、")}
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onUnlockAndRetry}
              className="rounded-md bg-warning/20 px-2 py-1 text-warning hover:bg-warning/30"
            >
              解锁并重试
            </button>
            <button
              type="button"
              onClick={onDismissConflict}
              className="rounded-md px-2 py-1 text-muted hover:bg-surface-2"
            >
              取消
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
