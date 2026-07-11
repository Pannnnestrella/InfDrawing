"use client";

import { useEffect, useState } from "react";

import { AlertIcon, SparklesIcon } from "@/components/icons";
import {
  featureReason,
  fetchCapabilities,
  type CapabilitiesResponse,
} from "@/lib/capabilities";

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

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (!disabled && prompt.trim()) onSubmit(prompt.trim());
    }
    if (event.key === "Escape") onCancel();
  }

  return (
    <div
      className="fixed inset-0 z-[10000] flex items-end justify-end bg-black/50 p-6 backdrop-blur-[2px]"
      role="dialog"
      aria-modal="true"
      aria-label="AI 生图"
      onClick={onCancel}
    >
      <div
        className="w-full max-w-md rounded-2xl border border-line bg-surface-1 p-4 shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-3 flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-surface-2 text-accent">
            <SparklesIcon size={16} />
          </span>
          <div>
            <h2 className="text-sm font-semibold text-ink">AI 生图</h2>
            <p className="text-[11px] text-muted">引擎：{backendLabel}</p>
          </div>
        </div>

        {disabledReason ? (
          <p className="mb-3 flex items-start gap-1.5 text-[11px] text-warning">
            <AlertIcon size={13} className="mt-px shrink-0" />
            {disabledReason}
          </p>
        ) : null}

        <textarea
          className="mb-3 min-h-[96px] w-full resize-none rounded-xl border border-line bg-surface-2 px-3 py-2.5 text-sm text-ink transition-colors placeholder:text-faint focus:border-accent focus:outline-none"
          placeholder="描述你想生成的内容…"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={handleKeyDown}
          autoFocus
        />

        <div className="flex justify-end gap-2">
          <button
            type="button"
            className="rounded-lg px-3 py-1.5 text-sm text-muted transition-colors hover:bg-surface-2 hover:text-ink"
            onClick={onCancel}
          >
            取消
          </button>
          <button
            type="button"
            className="rounded-lg bg-accent px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-40"
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
