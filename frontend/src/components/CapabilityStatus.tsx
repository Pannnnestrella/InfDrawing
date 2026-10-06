"use client";

import { useEffect, useState } from "react";

import { RefreshIcon } from "@/components/icons";
import {
  fetchCapabilities,
  tierLabel,
  type CapabilitiesResponse,
} from "@/lib/capabilities";

const REFRESH_MS = 60_000;

/** Compact environment chip for the panel header; click to expand details. */
export function CapabilityStatus() {
  const [caps, setCaps] = useState<CapabilitiesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);
  const [refreshTick, setRefreshTick] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const data = await fetchCapabilities();
        if (cancelled) return;
        setCaps(data);
        setError(null);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "探测失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    const timer = window.setInterval(() => void load(), REFRESH_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [refreshTick]);

  const comfyOk = caps?.services.comfyui.ok ?? false;
  const dotClass = loading
    ? "bg-muted"
    : error || !comfyOk
      ? "bg-danger"
      : "bg-success";

  const gpuLine = caps?.gpu.available
    ? `${caps.gpu.name ?? "GPU"} · ${caps.gpu.vram_free_mb ?? "?"} / ${caps.gpu.vram_total_mb ?? "?"} MB`
    : "未检测到 NVIDIA GPU";

  return (
    <div className="relative">
      <button
        type="button"
        className="flex items-center gap-1.5 rounded-full border border-line bg-surface-2 px-2.5 py-1 text-[11px] text-muted transition-colors hover:bg-surface-3 hover:text-ink"
        onClick={() => setExpanded((v) => !v)}
        title="环境状态"
      >
        <span className={`h-1.5 w-1.5 rounded-full ${dotClass}`} />
        {loading ? "探测中…" : caps ? tierLabel(caps.tier) : "环境异常"}
      </button>

      {expanded ? (
        <div className="absolute right-0 top-8 z-20 w-72 space-y-2 rounded-xl border border-line bg-surface-2 p-3 text-xs shadow-2xl">
          <div className="flex items-center justify-between">
            <span className="font-medium text-ink">环境状态</span>
            <button
              type="button"
              className="flex items-center gap-1 text-muted transition-colors hover:text-ink"
              onClick={() => {
                setLoading(true);
                setRefreshTick((n) => n + 1);
              }}
            >
              <RefreshIcon size={12} />
              刷新
            </button>
          </div>

          {caps ? (
            <ul className="space-y-1.5 text-muted">
              <li>GPU：{gpuLine}</li>
              <li>
                ComfyUI：
                {caps.services.comfyui.ok
                  ? `正常${caps.services.comfyui.remote ? "（远程）" : "（本地）"}`
                  : `不可达 ${caps.services.comfyui.url}`}
              </li>
              <li>
                DeepSeek：
                {caps.services.deepseek?.ok
                  ? "正常"
                  : caps.services.deepseek
                    ? "不可达 / 未配置"
                    : "未探测"}
              </li>
              <li>
                Ollama（可选）：
                {caps.services.ollama.ok ? "正常" : "未运行"}
              </li>
            </ul>
          ) : null}

          {error ? <p className="text-danger">{error}</p> : null}
          {!loading && caps && !comfyOk ? (
            <p className="text-warning">
              生图功能已禁用：请先启动 ComfyUI 或检查 INFD_COMFYUI_BASE_URL
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
