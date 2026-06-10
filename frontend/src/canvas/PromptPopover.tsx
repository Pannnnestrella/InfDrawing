"use client";

import { useEffect, useState } from "react";

import {
  featureReason,
  fetchCapabilities,
  type CapabilitiesResponse,
} from "@/lib/capabilities";
import { theme } from "@/lib/theme";

interface PromptPopoverProps {
  backendLabel: string;
  onSubmit: (prompt: string) => void;
  onCancel: () => void;
}

export function PromptPopover({
  backendLabel,
  onSubmit,
  onCancel,
}: PromptPopoverProps) {
  const [prompt, setPrompt] = useState("");
  const [caps, setCaps] = useState<CapabilitiesResponse | null>(null);

  useEffect(() => {
    void fetchCapabilities().then(setCaps).catch(() => setCaps(null));
  }, []);

  const disabledReason = featureReason(caps, "txt2img");
  const disabled = Boolean(disabledReason);

  return (
    <div
      className="fixed inset-0 z-[10000] flex items-end justify-end bg-black/40 p-6"
      role="dialog"
      aria-modal="true"
      aria-label="AI 生图"
      onClick={onCancel}
    >
      <div
        className="w-full max-w-md rounded-lg border p-4 shadow-xl"
        style={{ background: theme.surface, borderColor: theme.border }}
        onClick={(event) => event.stopPropagation()}
      >
        <h2 className="mb-1 text-base font-semibold" style={{ color: theme.textPrimary }}>
          AI 生图
        </h2>
        <p className="mb-3 text-xs" style={{ color: theme.textMuted }}>
          引擎：{backendLabel}
        </p>

        {disabledReason ? (
          <p className="mb-3 text-xs text-amber-400/90">{disabledReason}</p>
        ) : null}

        <textarea
          className="mb-3 min-h-[96px] w-full resize-none rounded-md border px-3 py-2 text-sm"
          style={{
            background: theme.surface,
            borderColor: theme.border,
            color: theme.textPrimary,
          }}
          placeholder="描述你想生成的内容…"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          autoFocus
        />

        <div className="flex justify-end gap-2">
          <button
            type="button"
            className="rounded px-3 py-1.5 text-sm"
            style={{ color: theme.textMuted }}
            onClick={onCancel}
          >
            取消
          </button>
          <button
            type="button"
            className="rounded px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            style={{ background: theme.accent }}
            disabled={disabled || !prompt.trim()}
            onClick={() => onSubmit(prompt.trim())}
          >
            生成
          </button>
        </div>
      </div>
    </div>
  );
}
