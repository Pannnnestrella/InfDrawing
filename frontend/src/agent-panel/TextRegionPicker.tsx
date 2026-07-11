"use client";

import { Spinner } from "@/components/Spinner";
import type { TextRegion } from "@/lib/api";

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
      <p className="flex items-center gap-2 text-[11px] text-muted">
        <Spinner size={12} />
        正在检测文字…
      </p>
    );
  }

  if (error || regions.length === 0) {
    return (
      <div className="space-y-1.5 text-[11px]">
        <p className={error ? "text-danger" : "text-muted"}>
          {error ?? "未检测到文字，请换一张含文字的图片"}
        </p>
        <button
          type="button"
          className="rounded-md border border-line px-2 py-1 text-muted transition-colors hover:bg-surface-3 hover:text-ink"
          onClick={onRetry}
        >
          重新检测
        </button>
      </div>
    );
  }

  return (
    <div className="panel-scroll max-h-36 space-y-1 overflow-y-auto text-xs">
      <p className="text-[11px] text-muted">选择要替换的文字块：</p>
      {regions.map((region, index) => {
        const active = selectedIndex === index;
        return (
          <button
            key={`${region.text}-${index}`}
            type="button"
            className={`w-full rounded-lg border px-2.5 py-1.5 text-left transition-colors ${
              active
                ? "border-accent bg-accent/10 text-ink"
                : "border-line bg-surface-2 text-ink hover:bg-surface-3"
            }`}
            onClick={() => onSelect(index)}
          >
            <span className="line-clamp-2">{region.text}</span>
            <span className="mt-0.5 block text-[10px] text-faint">
              置信度 {(region.confidence * 100).toFixed(0)}%
            </span>
          </button>
        );
      })}
    </div>
  );
}
