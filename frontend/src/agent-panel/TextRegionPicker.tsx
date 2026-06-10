"use client";

import type { TextRegion } from "@/lib/api";
import { theme } from "@/lib/theme";

interface TextRegionPickerProps {
  regions: TextRegion[];
  selectedIndex: number | null;
  loading: boolean;
  error: string | null;
  onSelect: (index: number) => void;
  onRetry: () => void;
}

export function TextRegionPicker({
  regions,
  selectedIndex,
  loading,
  error,
  onSelect,
  onRetry,
}: TextRegionPickerProps) {
  if (loading) {
    return (
      <p className="text-xs" style={{ color: theme.textMuted }}>
        正在检测文字…
      </p>
    );
  }

  if (error) {
    return (
      <div className="space-y-2 text-xs">
        <p className="text-red-400">{error}</p>
        <button
          type="button"
          className="rounded-md border px-2 py-1"
          style={{ borderColor: theme.border, color: theme.textMuted }}
          onClick={onRetry}
        >
          重新检测
        </button>
      </div>
    );
  }

  if (regions.length === 0) {
    return (
      <div className="space-y-2 text-xs" style={{ color: theme.textMuted }}>
        <p>未检测到文字，请换一张含文字的图片</p>
        <button
          type="button"
          className="rounded-md border px-2 py-1"
          style={{ borderColor: theme.border }}
          onClick={onRetry}
        >
          重新检测
        </button>
      </div>
    );
  }

  return (
    <div className="max-h-36 space-y-1 overflow-y-auto text-xs">
      <p style={{ color: theme.textMuted }}>选择要替换的文字块：</p>
      {regions.map((region, index) => {
        const active = selectedIndex === index;
        return (
          <button
            key={`${region.text}-${index}`}
            type="button"
            className="w-full rounded-md border px-2 py-1.5 text-left transition-colors"
            style={{
              borderColor: active ? theme.accent : theme.border,
              background: active ? `${theme.accent}22` : theme.surface,
              color: theme.textPrimary,
            }}
            onClick={() => onSelect(index)}
          >
            <span className="line-clamp-2">{region.text}</span>
            <span className="mt-0.5 block text-[10px]" style={{ color: theme.textMuted }}>
              置信度 {(region.confidence * 100).toFixed(0)}%
            </span>
          </button>
        );
      })}
    </div>
  );
}
