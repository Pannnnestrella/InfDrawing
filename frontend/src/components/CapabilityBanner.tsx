"use client";

import { useCallback, useEffect, useState } from "react";

import {
  fetchCapabilities,
  tierLabel,
  type CapabilitiesResponse,
} from "@/lib/capabilities";
import { theme } from "@/lib/theme";

const REFRESH_MS = 60_000;

export function CapabilityBanner() {
  const [caps, setCaps] = useState<CapabilitiesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const data = await fetchCapabilities();
      setCaps(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "探测失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const gpuLine = caps?.gpu.available
    ? `${caps.gpu.name ?? "GPU"} · ${caps.gpu.vram_free_mb ?? "?"} / ${caps.gpu.vram_total_mb ?? "?"} MB`
    : "未检测到 NVIDIA GPU";

  const comfyLine = caps?.services.comfyui.ok
    ? `ComfyUI ✓ ${caps.services.comfyui.remote ? "（远程）" : "（本地）"}`
    : `ComfyUI ✗ ${caps?.services.comfyui.url ?? ""}`;

  return (
    <div
      className="border-b px-4 py-2 text-xs"
      style={{
        borderColor: theme.border,
        background: theme.surface,
        color: theme.textMuted,
      }}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span style={{ color: theme.textPrimary }}>
          环境
          {loading ? " · 探测中…" : caps ? ` · ${tierLabel(caps.tier)}` : ""}
        </span>
        <button
          type="button"
          className="underline"
          style={{ color: theme.accent }}
          onClick={() => {
            setLoading(true);
            void refresh();
          }}
        >
          刷新
        </button>
      </div>
      {!loading && caps ? (
        <p className="mt-1">
          {gpuLine} · {comfyLine}
        </p>
      ) : null}
      {error ? <p className="mt-1 text-red-400">{error}</p> : null}
      {!loading && caps && !caps.services.comfyui.ok ? (
        <p className="mt-1 text-amber-400/90">
          生图功能已禁用：请先启动 ComfyUI 或检查 INFD_COMFYUI_BASE_URL
        </p>
      ) : null}
    </div>
  );
}
