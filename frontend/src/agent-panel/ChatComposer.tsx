"use client";

import {
  AlertIcon,
  BrushIcon,
  CheckIcon,
  GitBranchIcon,
  ImageIcon,
  SendIcon,
} from "@/components/icons";
import { Spinner } from "@/components/Spinner";
import type { TextRegion } from "@/lib/api";
import type { CapabilitiesResponse } from "@/lib/capabilities";

import { EngineSelect } from "./EngineSelect";
import { ModeChips } from "./ModeChips";
import { TextRegionPicker } from "./TextRegionPicker";
import type { ChatMode } from "./types";
import type { EnginePreference } from "@/lib/engine-preference";

interface ChatComposerProps {
  message: string;
  mode: ChatMode;
  capabilities: CapabilitiesResponse | null;
  enginePreference: EnginePreference;
  busy: boolean;
  modeEnabled: boolean;
  modeDisabledReason: string | null;
  selectionHint: string | null;
  canvasReady: boolean;
  canvasHasSelection: boolean;
  canvasHasMask: boolean;
  textRegions: TextRegion[];
  selectedTextIndex: number | null;
  ocrLoading: boolean;
  ocrError: string | null;
  onMessageChange: (value: string) => void;
  onModeChange: (mode: ChatMode) => void;
  onEngineChange: (value: EnginePreference) => void;
  onSubmit: () => void;
  onOpenMaskEditor: () => void;
  onSelectTextRegion: (index: number) => void;
  onRetryOcr: () => void;
  onOpenStudio?: () => void;
  onOpenLibrary?: () => void;
}

const PLACEHOLDERS: Record<ChatMode, string> = {
  auto: "描述你想对画布执行的操作…",
  txt2img: "描述你想生成的内容…",
  inpaint: "描述重绘区域要变成什么，例如：一颗鲜红的苹果",
  image_edit: "描述要如何修改选中图片，例如：把天空改成晚霞",
  decompose: "可选：描述期望的背景风格，留空则使用默认",
  text_edit: "输入替换后的新文字…",
};

export function ChatComposer({
  message,
  mode,
  capabilities,
  enginePreference,
  busy,
  modeEnabled,
  modeDisabledReason,
  selectionHint,
  canvasReady,
  canvasHasSelection,
  canvasHasMask,
  textRegions,
  selectedTextIndex,
  ocrLoading,
  ocrError,
  onMessageChange,
  onModeChange,
  onEngineChange,
  onSubmit,
  onOpenMaskEditor,
  onSelectTextRegion,
  onRetryOcr,
  onOpenStudio,
  onOpenLibrary,
}: ChatComposerProps) {
  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (!busy && modeEnabled) onSubmit();
    }
  }

  return (
    <div className="shrink-0 space-y-2.5 border-t border-line px-3 pb-3 pt-2.5">
      <ModeChips mode={mode} capabilities={capabilities} onModeChange={onModeChange} />
      {onOpenStudio || onOpenLibrary ? (
        <div className="flex gap-2">
          {onOpenStudio ? (
            <button
              type="button"
              className="flex flex-1 items-center justify-center gap-2 rounded-lg border border-line bg-surface-2 px-3 py-2 text-xs font-medium text-ink transition-colors hover:bg-surface-3"
              onClick={onOpenStudio}
            >
              <GitBranchIcon size={14} className="text-accent-hover" />
              多轮编辑
            </button>
          ) : null}
          {onOpenLibrary ? (
            <button
              type="button"
              className="flex flex-1 items-center justify-center gap-2 rounded-lg border border-line bg-surface-2 px-3 py-2 text-xs font-medium text-ink transition-colors hover:bg-surface-3"
              onClick={onOpenLibrary}
            >
              <ImageIcon size={14} className="text-accent-hover" />
              素材库
            </button>
          ) : null}
        </div>
      ) : null}
      {(mode === "auto" || mode === "txt2img" || mode === "inpaint") ? (
        <EngineSelect
          preference={enginePreference}
          capabilities={capabilities}
          disabled={busy}
          onChange={onEngineChange}
        />
      ) : null}

      {modeDisabledReason ? (
        <p className="flex items-start gap-1.5 text-[11px] text-warning">
          <AlertIcon size={13} className="mt-px shrink-0" />
          {modeDisabledReason}
        </p>
      ) : null}

      {mode === "inpaint" || (mode === "auto" && canvasHasSelection) ? (
        <div className="space-y-1.5">
          {mode === "inpaint" && selectionHint ? (
            <p className="text-[11px] text-muted">{selectionHint}</p>
          ) : null}
          <button
            type="button"
            className="flex w-full items-center justify-center gap-2 rounded-lg border border-line bg-surface-2 px-3 py-2 text-xs font-medium text-ink transition-colors hover:bg-surface-3 disabled:cursor-not-allowed disabled:opacity-40"
            disabled={!canvasReady || !canvasHasSelection || busy}
            onClick={onOpenMaskEditor}
          >
            <BrushIcon size={14} className="text-accent-hover" />
            {mode === "auto" ? "准备局部重绘 Mask（可选）" : "刷选 Mask（画布）"}
          </button>
          {canvasHasMask ? (
            <p className="flex items-center gap-1.5 text-[11px] text-success">
              <CheckIcon size={13} />
              Mask 已就绪
            </p>
          ) : null}
        </div>
      ) : null}

      {mode === "image_edit" || mode === "decompose" || mode === "text_edit" ? (
        <p className="text-[11px] text-muted">
          {mode === "image_edit"
            ? selectionHint ?? "请选中一张图片，然后用文字描述修改需求（OpenAI）"
            : (selectionHint ?? "请在画布上选中一张图片")}
        </p>
      ) : null}

      {mode === "text_edit" ||
      (mode === "auto" &&
        canvasHasSelection &&
        (ocrLoading || Boolean(ocrError) || textRegions.length > 0)) ? (
        <TextRegionPicker
          regions={textRegions}
          selectedIndex={selectedTextIndex}
          loading={ocrLoading}
          error={ocrError}
          onSelect={onSelectTextRegion}
          onRetry={onRetryOcr}
        />
      ) : null}

      <div className="rounded-xl border border-line bg-surface-2 transition-colors focus-within:border-accent">
        <textarea
          className="min-h-[60px] w-full resize-none bg-transparent px-3 pt-2.5 text-sm text-ink placeholder:text-faint focus:outline-none disabled:opacity-50"
          placeholder={PLACEHOLDERS[mode]}
          value={message}
          disabled={busy}
          onChange={(e) => onMessageChange(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <div className="flex items-center justify-between px-2 pb-2 pl-3">
          <span className="text-[10px] text-faint">Enter 发送 · Shift+Enter 换行</span>
          <button
            type="button"
            aria-label="发送"
            className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent text-white transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-40"
            disabled={busy || !modeEnabled}
            onClick={onSubmit}
          >
            {busy ? <Spinner size={14} className="border-white/30 border-t-white" /> : <SendIcon size={15} />}
          </button>
        </div>
      </div>
    </div>
  );
}
