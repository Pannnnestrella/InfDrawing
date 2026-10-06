"use client";

import type { CapabilitiesResponse } from "@/lib/capabilities";
import {
  cloudBackends,
  hasLocalImageBackend,
  type CloudProvider,
  type EngineMode,
  type EnginePreference,
} from "@/lib/engine-preference";

interface EngineSelectProps {
  preference: EnginePreference;
  capabilities: CapabilitiesResponse | null;
  disabled?: boolean;
  onChange: (next: EnginePreference) => void;
}

const MODE_OPTIONS: { id: EngineMode; label: string }[] = [
  { id: "auto", label: "自动" },
  { id: "local", label: "本地" },
  { id: "cloud", label: "云端" },
];

const CLOUD_OPTIONS: { id: CloudProvider; label: string }[] = [
  { id: "openai", label: "OpenAI" },
  { id: "dashscope", label: "万相" },
];

export function EngineSelect({
  preference,
  capabilities,
  disabled = false,
  onChange,
}: EngineSelectProps) {
  const localOk = hasLocalImageBackend(capabilities);
  const clouds = cloudBackends(capabilities);
  const cloudOk = clouds.length > 0;

  return (
    <div className="space-y-1.5">
      <div className="grid grid-cols-3 gap-1 rounded-xl bg-surface-2 p-1">
        {MODE_OPTIONS.map((item) => {
          const enabled =
            item.id === "auto" ||
            (item.id === "local" && localOk) ||
            (item.id === "cloud" && cloudOk);
          const active = preference.mode === item.id;
          return (
            <button
              key={item.id}
              type="button"
              title={
                !enabled
                  ? item.id === "local"
                    ? "本地 ComfyUI 不可用"
                    : "未配置云端图像 API Key"
                  : item.label
              }
              disabled={disabled || !enabled}
              className={`rounded-lg px-1 py-1.5 text-[11px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-35 ${
                active
                  ? "bg-surface-3 text-ink shadow-sm"
                  : "text-muted hover:text-ink"
              }`}
              onClick={() => onChange({ ...preference, mode: item.id })}
            >
              {item.label}
            </button>
          );
        })}
      </div>

      {preference.mode === "cloud" ? (
        <div className="grid grid-cols-2 gap-1 rounded-xl bg-surface-2 p-1">
          {CLOUD_OPTIONS.map((item) => {
            const enabled = clouds.includes(item.id);
            const active = preference.cloudProvider === item.id;
            return (
              <button
                key={item.id}
                type="button"
                title={!enabled ? "未配置该厂商 API Key" : item.label}
                disabled={disabled || !enabled}
                className={`rounded-lg px-1 py-1.5 text-[11px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-35 ${
                  active
                    ? "bg-surface-3 text-ink shadow-sm"
                    : "text-muted hover:text-ink"
                }`}
                onClick={() =>
                  onChange({ ...preference, cloudProvider: item.id })
                }
              >
                {item.label}
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
