"use client";

import { BrushIcon, ImageIcon, LayersIcon, TypeIcon } from "@/components/icons";
import type { CapabilitiesResponse } from "@/lib/capabilities";
import { featureReason, isModeEnabled } from "@/lib/capabilities";

import { MODE_LABELS, MODE_ORDER, type ChatMode } from "./types";

const MODE_ICONS: Record<ChatMode, typeof ImageIcon> = {
  txt2img: ImageIcon,
  inpaint: BrushIcon,
  decompose: LayersIcon,
  text_edit: TypeIcon,
};

interface ModeChipsProps {
  mode: ChatMode;
  capabilities: CapabilitiesResponse | null;
  onModeChange: (mode: ChatMode) => void;
}

export function ModeChips({ mode, capabilities, onModeChange }: ModeChipsProps) {
  return (
    <div className="grid grid-cols-4 gap-1 rounded-xl bg-surface-2 p-1">
      {MODE_ORDER.map((item) => {
        const enabled = isModeEnabled(capabilities, item);
        const reason = featureReason(capabilities, item);
        const active = mode === item;
        const Icon = MODE_ICONS[item];

        return (
          <button
            key={item}
            type="button"
            title={!enabled ? (reason ?? "不可用") : MODE_LABELS[item]}
            disabled={!enabled}
            className={`flex flex-col items-center gap-1 rounded-lg px-1 py-1.5 text-[11px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-35 ${
              active
                ? "bg-surface-3 text-ink shadow-sm"
                : "text-muted hover:text-ink"
            }`}
            onClick={() => onModeChange(item)}
          >
            <Icon size={15} className={active ? "text-accent-hover" : undefined} />
            {MODE_LABELS[item]}
          </button>
        );
      })}
    </div>
  );
}
