"use client";

import { useState } from "react";

import {
  AlertIcon,
  BrushIcon,
  CheckIcon,
  GitBranchIcon,
  ImageIcon,
  LayersIcon,
  SendIcon,
} from "@/components/icons";
import { Spinner } from "@/components/Spinner";
import type { SelectedImageChip } from "@/canvas/types";
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
  selectedImage?: SelectedImageChip | null;
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
  onOpenLayers?: () => void;
}

const PLACEHOLDERS: Record<ChatMode, string> = {
  auto: "描述你想对画布执行的操作…",
  txt2img: "描述你想生成的内容…",
  inpaint: "描述重绘区域要变成什么，例如：一颗鲜红的苹果",
  image_edit: "描述要如何修改选中图片，例如：把天空改成晚霞",
  decompose: "留空：拆成主体和背景。或写下要拆开的物体，例如「剑、盾」",
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
  selectedImage = null,
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
  onOpenLayers,
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
      {onOpenStudio || onOpenLibrary || onOpenLayers ? (
        <div className="flex flex-wrap gap-2">
          {onOpenStudio ? (
            <button
              type="button"
              className="flex min-w-[30%] flex-1 items-center justify-center gap-2 rounded-lg border border-line bg-surface-2 px-3 py-2 text-xs font-medium text-ink transition-colors hover:bg-surface-3"
              onClick={onOpenStudio}
            >
              <GitBranchIcon size={14} className="text-accent-hover" />
              多轮编辑
            </button>
          ) : null}
          {onOpenLibrary ? (
            <button
              type="button"
              className="flex min-w-[30%] flex-1 items-center justify-center gap-2 rounded-lg border border-line bg-surface-2 px-3 py-2 text-xs font-medium text-ink transition-colors hover:bg-surface-3"
              onClick={onOpenLibrary}
            >
              <ImageIcon size={14} className="text-accent-hover" />
              素材库
            </button>
          ) : null}
          {onOpenLayers ? (
            <button
              type="button"
              className="flex min-w-[30%] flex-1 items-center justify-center gap-2 rounded-lg border border-line bg-surface-2 px-3 py-2 text-xs font-medium text-ink transition-colors hover:bg-surface-3"
              onClick={onOpenLayers}
            >
              <LayersIcon size={14} className="text-accent-hover" />
              图层
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
            {mode === "auto" ? "打开 Mask 重绘（可选）" : "打开 Mask 重绘"}
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
        <p className={`text-[11px] ${selectionHint ? "text-warning" : "text-muted"}`}>
          {selectionHint
            ? selectionHint
            : mode === "image_edit"
              ? "已选中图片，用文字描述修改需求（通义 Qwen）"
              : mode === "text_edit"
                ? "已选中图片，可检测并替换文字"
                : "已选中图片。留空拆成主体和背景；写下物体名称则逐个拆开，例如「剑、盾」"}
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
        {selectedImage ? (
          <div className="px-2.5 pt-2.5">
            <SelectedImageChipView image={selectedImage} />
          </div>
        ) : null}
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

function SelectedImageChipView({ image }: { image: SelectedImageChip }) {
  const [open, setOpen] = useState(false);

  return (
    <div
      className="relative inline-flex max-w-full"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      {open && image.thumbSrc ? (
        <div className="pointer-events-none absolute bottom-full left-0 z-20 mb-2 w-48 overflow-hidden rounded-xl border border-line bg-surface-1 p-1 shadow-xl">
          {/* Canvas selection preview; the chip already names the image. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={image.thumbSrc}
            alt={`${image.name} 预览`}
            className="h-44 w-full rounded-lg bg-surface-2 object-contain"
          />
        </div>
      ) : null}
      <div
        className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-line bg-surface-1 py-1 pl-1 pr-2.5 text-[11px] text-muted"
        aria-label={image.name}
        title={image.name}
      >
        {image.thumbSrc ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={image.thumbSrc} alt="" className="h-5 w-5 shrink-0 rounded-full object-cover" />
        ) : (
          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-surface-3 text-faint">
            <ImageIcon size={12} />
          </span>
        )}
        <span className="max-w-[180px] truncate">{image.name}</span>
      </div>
    </div>
  );
}
