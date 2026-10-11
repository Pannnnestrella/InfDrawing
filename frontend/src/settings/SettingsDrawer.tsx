"use client";

import { useEffect, useMemo, useState } from "react";

import { EngineSelect } from "@/agent-panel/EngineSelect";
import { ApiKeySection } from "@/components/ApiKeySection";
import { CloseIcon, RefreshIcon, SettingsIcon } from "@/components/icons";
import {
  fetchCapabilities,
  tierLabel,
  type CapabilitiesResponse,
} from "@/lib/capabilities";
import type { EnginePreference } from "@/lib/engine-preference";
import {
  imageProviderLabel,
  loadImageProvider,
  loadPromptStyle,
  parseImageOptions,
  promptStyleLabel,
  saveImageProvider,
  savePromptStyle,
  subscribeCeditOptions,
  type ImageProviderOption,
  type PromptStyleOption,
} from "@/studio/studio-turn-options";

const DRAWER_Z = "z-[720]";

interface SettingsDrawerProps {
  open: boolean;
  onClose: () => void;
  enginePreference: EnginePreference;
  onEngineChange: (next: EnginePreference) => void;
  /** Optional prefetched caps; drawer still refreshes on open. */
  capabilities?: CapabilitiesResponse | null;
}

export function SettingsDrawer({
  open,
  onClose,
  enginePreference,
  onEngineChange,
  capabilities: capsProp = null,
}: SettingsDrawerProps) {
  const [caps, setCaps] = useState<CapabilitiesResponse | null>(capsProp);
  const [capsError, setCapsError] = useState<string | null>(null);
  const [capsLoading, setCapsLoading] = useState(false);
  const [promptStyle, setPromptStyle] = useState<PromptStyleOption>("preserve");
  const [imageProvider, setImageProvider] = useState<ImageProviderOption>("dashscope");

  const imageOptions = useMemo(
    () => parseImageOptions(caps?.features.controlled_edit?.models?.image_options),
    [caps],
  );

  const ceditModels = caps?.features.controlled_edit?.models;

  useEffect(() => {
    if (capsProp) setCaps(capsProp);
  }, [capsProp]);

  useEffect(() => {
    if (!open) return;

    function syncCedit() {
      const models = caps?.features.controlled_edit?.models ?? {};
      const options = parseImageOptions(models.image_options);
      const fallbackStyle =
        models.prompt_style === "target_only" || models.prompt_style === "preserve"
          ? models.prompt_style
          : "preserve";
      const fallbackProvider =
        models.image_provider === "openai" || models.image_provider === "dashscope"
          ? models.image_provider
          : "dashscope";
      setPromptStyle(loadPromptStyle(fallbackStyle));
      setImageProvider(loadImageProvider(options, fallbackProvider));
    }

    syncCedit();
    return subscribeCeditOptions(syncCedit);
  }, [open, caps]);

  useEffect(() => {
    if (!open) return;

    let cancelled = false;
    async function load() {
      setCapsLoading(true);
      try {
        const data = await fetchCapabilities();
        if (cancelled) return;
        setCaps(data);
        setCapsError(null);
      } catch (err) {
        if (cancelled) return;
        setCapsError(err instanceof Error ? err.message : "探测失败");
      } finally {
        if (!cancelled) setCapsLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const comfyOk = caps?.services.comfyui.ok ?? false;
  const gpuLine = caps?.gpu.available
    ? `${caps.gpu.name ?? "GPU"} · ${caps.gpu.vram_free_mb ?? "?"} / ${caps.gpu.vram_total_mb ?? "?"} MB`
    : "未检测到 NVIDIA GPU";

  return (
    <div className={`fixed inset-0 ${DRAWER_Z}`}>
      <button
        type="button"
        aria-label="关闭设置"
        className="absolute inset-0 bg-black/35 backdrop-blur-[1px]"
        onClick={onClose}
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby="infd-settings-title"
        className="absolute bottom-0 right-0 top-0 flex w-full max-w-[380px] flex-col border-l border-line bg-surface-1 shadow-2xl"
      >
        <header className="flex shrink-0 items-center justify-between gap-2 border-b border-line px-4 py-3">
          <div className="flex items-center gap-2">
            <SettingsIcon size={16} className="text-accent" />
            <h2 id="infd-settings-title" className="text-sm font-semibold text-ink">
              设置
            </h2>
          </div>
          <button
            type="button"
            aria-label="关闭"
            className="rounded-lg p-1.5 text-muted transition-colors hover:bg-surface-2 hover:text-ink"
            onClick={onClose}
          >
            <CloseIcon size={16} />
          </button>
        </header>

        <div className="panel-scroll flex-1 space-y-6 overflow-y-auto px-4 py-4">
          <section className="space-y-2">
            <h3 className="text-xs font-semibold tracking-wide text-ink">访问凭证</h3>
            <ApiKeySection />
          </section>

          <section className="space-y-2">
            <h3 className="text-xs font-semibold tracking-wide text-ink">生图引擎</h3>
            <p className="text-[11px] text-muted">
              影响文生图 / 局部重绘的 backend 选择；与对话栏引擎选择同步。
            </p>
            <EngineSelect
              preference={enginePreference}
              capabilities={caps}
              onChange={onEngineChange}
            />
          </section>

          <section className="space-y-2">
            <h3 className="text-xs font-semibold tracking-wide text-ink">可控编辑</h3>
            <p className="text-[11px] text-muted">
              用于多轮可控编辑请求；与 Studio 下拉选项共用会话偏好。
            </p>
            <div className="grid grid-cols-2 gap-2">
              <label className="space-y-1 text-[10px] text-faint">
                <span>提示词策略</span>
                <select
                  value={promptStyle}
                  onChange={(event) => {
                    const style = event.target.value as PromptStyleOption;
                    setPromptStyle(style);
                    savePromptStyle(style);
                  }}
                  className="w-full rounded-md border border-line bg-surface-2 px-2 py-1.5 text-xs text-ink outline-none focus:border-accent"
                >
                  <option value="preserve">{promptStyleLabel("preserve")}</option>
                  <option value="target_only">{promptStyleLabel("target_only")}</option>
                </select>
              </label>
              <label className="space-y-1 text-[10px] text-faint">
                <span>生图提供商</span>
                <select
                  value={imageProvider}
                  disabled={imageOptions.length === 0}
                  onChange={(event) => {
                    const provider = event.target.value as ImageProviderOption;
                    setImageProvider(provider);
                    saveImageProvider(provider);
                  }}
                  className="w-full rounded-md border border-line bg-surface-2 px-2 py-1.5 text-xs text-ink outline-none focus:border-accent disabled:opacity-50"
                >
                  {imageOptions.length === 0 ? (
                    <option value={imageProvider}>暂无可用模型</option>
                  ) : (
                    imageOptions.map((option) => (
                      <option key={option.provider} value={option.provider}>
                        {option.label}
                      </option>
                    ))
                  )}
                </select>
              </label>
            </div>
            {ceditModels ? (
              <ul className="space-y-1 rounded-lg border border-line bg-surface-2 px-2.5 py-2 text-[11px] text-muted">
                <li>场景 / 视觉：{ceditModels.scene ?? "—"} · {ceditModels.vision ?? "—"}</li>
                <li>
                  默认图像：{ceditModels.image ?? "—"}
                  {ceditModels.image_provider === "openai" ||
                  ceditModels.image_provider === "dashscope"
                    ? `（${imageProviderLabel(ceditModels.image_provider)}）`
                    : ceditModels.image_provider
                      ? `（${ceditModels.image_provider}）`
                      : ""}
                </li>
                <li>Lock paste：{ceditModels.lock_paste ?? "—"}</li>
              </ul>
            ) : null}
          </section>

          <section className="space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-semibold tracking-wide text-ink">环境状态</h3>
              <button
                type="button"
                className="flex items-center gap-1 text-[11px] text-muted transition-colors hover:text-ink"
                onClick={() => {
                  setCapsLoading(true);
                  void fetchCapabilities()
                    .then((data) => {
                      setCaps(data);
                      setCapsError(null);
                    })
                    .catch((err: unknown) => {
                      setCapsError(err instanceof Error ? err.message : "探测失败");
                    })
                    .finally(() => setCapsLoading(false));
                }}
              >
                <RefreshIcon size={12} />
                {capsLoading ? "探测中…" : "刷新"}
              </button>
            </div>
            {caps ? (
              <ul className="space-y-1.5 text-[11px] text-muted">
                <li>档位：{tierLabel(caps.tier)}</li>
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
                  OpenAI Images：
                  {caps.services.openai_images?.ok ? "已配置" : "未配置 / 不可用"}
                </li>
                <li>
                  DashScope：
                  {caps.services.dashscope?.ok ? "已配置" : "未配置 / 不可用"}
                </li>
                <li>Ollama：{caps.services.ollama.ok ? "正常" : "未运行"}</li>
              </ul>
            ) : null}
            {capsError ? <p className="text-[11px] text-danger">{capsError}</p> : null}
            {caps && !comfyOk ? (
              <p className="text-[11px] text-warning">
                本地生图可能不可用：请启动 ComfyUI 或改用云端引擎。
              </p>
            ) : null}
          </section>
        </div>
      </aside>
    </div>
  );
}

/** Compact header chip that opens the settings drawer. */
export function SettingsTrigger({
  onClick,
  configuredApiKey,
}: {
  onClick: () => void;
  configuredApiKey?: boolean;
}) {
  return (
    <button
      type="button"
      className="flex items-center gap-1.5 rounded-full border border-line bg-surface-2 px-2.5 py-1 text-[11px] text-muted transition-colors hover:bg-surface-3 hover:text-ink"
      title="设置"
      aria-label="打开设置"
      onClick={onClick}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          configuredApiKey ? "bg-success" : "bg-muted"
        }`}
      />
      <SettingsIcon size={12} />
      设置
    </button>
  );
}
