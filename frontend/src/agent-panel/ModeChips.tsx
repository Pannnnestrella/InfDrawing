"use client";

import type { CapabilitiesResponse } from "@/lib/capabilities";
import { featureReason, isModeEnabled } from "@/lib/capabilities";
import { theme } from "@/lib/theme";

import { MODE_LABELS, MODE_ORDER, type ChatMode } from "./types";

interface ModeChipsProps {
  mode: ChatMode;
  capabilities: CapabilitiesResponse | null;
  onModeChange: (mode: ChatMode) => void;
}

export function ModeChips({ mode, capabilities, onModeChange }: ModeChipsProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {MODE_ORDER.map((item) => {
        const enabled = isModeEnabled(capabilities, item);
        const reason = featureReason(
          capabilities,
          item === "txt2img"
            ? "txt2img"
            : item === "inpaint"
              ? "inpaint"
              : item === "decompose"
                ? "decompose"
                : "text_edit",
        );
        const active = mode === item;

        return (
          <button
            key={item}
            type="button"
            title={!enabled ? (reason ?? "不可用") : undefined}
            disabled={!enabled}
            className="rounded-full border px-3 py-1 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40"
            style={{
              borderColor: active ? theme.accent : theme.border,
              background: active ? `${theme.accent}22` : theme.surface,
              color: active ? theme.textPrimary : theme.textMuted,
            }}
            onClick={() => onModeChange(item)}
          >
            {MODE_LABELS[item]}
          </button>
        );
      })}
    </div>
  );
}
