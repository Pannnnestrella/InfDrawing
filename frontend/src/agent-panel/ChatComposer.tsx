"use client";

import type { TextRegion } from "@/lib/api";
import type { CapabilitiesResponse } from "@/lib/capabilities";
import { theme } from "@/lib/theme";

import { ModeChips } from "./ModeChips";
import { TextRegionPicker } from "./TextRegionPicker";
import type { ChatMode } from "./types";

interface ChatComposerProps {
  message: string;
  mode: ChatMode;
  capabilities: CapabilitiesResponse | null;
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
  onSubmit: () => void;
  onOpenMaskEditor: () => void;
  onSelectTextRegion: (index: number) => void;
  onRetryOcr: () => void;
}

const PLACEHOLDERS: Record<ChatMode, string> = {
  txt2img: "描述你想生成的内容…",
  inpaint: "描述重绘区域要变成什么，例如：一颗鲜红的苹果",
  decompose: "可选：描述期望的背景风格，留空则使用默认",
  text_edit: "输入替换后的新文字…",
};

export function ChatComposer({
  message,
  mode,
  capabilities,
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
  onSubmit,
  onOpenMaskEditor,
  onSelectTextRegion,
  onRetryOcr,
}: ChatComposerProps) {
  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (!busy && modeEnabled) onSubmit();
    }
  }

  return (
    <div
      className="shrink-0 space-y-3 border-t px-4 py-3"
      style={{ borderColor: theme.border, background: "var(--bg-panel)" }}
    >
      <ModeChips mode={mode} capabilities={capabilities} onModeChange={onModeChange} />

      {modeDisabledReason ? (
        <p className="text-xs text-amber-400/90">{modeDisabledReason}</p>
      ) : null}

      {mode === "inpaint" ? (
        <div className="space-y-2 text-xs" style={{ color: theme.textMuted }}>
          {selectionHint ? <p>{selectionHint}</p> : null}
          <button
            type="button"
            className="w-full rounded-md px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
            style={{ background: theme.accent }}
            disabled={!canvasReady || !canvasHasSelection || busy}
            onClick={onOpenMaskEditor}
          >
            刷选 Mask（画布）
          </button>
          {canvasHasMask ? <p className="text-emerald-400/90">Mask 已就绪</p> : null}
        </div>
      ) : null}

      {mode === "decompose" || mode === "text_edit" ? (
        <p className="text-xs" style={{ color: theme.textMuted }}>
          {selectionHint ?? "请在画布上选中一张图片"}
        </p>
      ) : null}

      {mode === "text_edit" ? (
        <TextRegionPicker
          regions={textRegions}
          selectedIndex={selectedTextIndex}
          loading={ocrLoading}
          error={ocrError}
          onSelect={onSelectTextRegion}
          onRetry={onRetryOcr}
        />
      ) : null}

      <textarea
        className="min-h-[72px] w-full resize-none rounded-md border px-3 py-2 text-sm"
        style={{
          background: theme.surface,
          borderColor: theme.border,
          color: theme.textPrimary,
        }}
        placeholder={PLACEHOLDERS[mode]}
        value={message}
        disabled={busy}
        onChange={(e) => onMessageChange(e.target.value)}
        onKeyDown={handleKeyDown}
      />

      <button
        type="button"
        className="w-full rounded-md px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        style={{ background: theme.accent }}
        disabled={busy || !modeEnabled}
        onClick={onSubmit}
      >
        发送
      </button>
    </div>
  );
}
