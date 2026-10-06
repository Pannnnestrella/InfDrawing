/** Persist and resolve the image engine preference for txt2img / inpaint. */

import type { CapabilitiesResponse } from "@/lib/capabilities";

export type EngineMode = "auto" | "local" | "cloud";
export type CloudProvider = "openai" | "dashscope";
/** Value sent to `/generate/*` as `backend`. */
export type ImageBackend = "auto" | "local" | "openai" | "dashscope";

const STORAGE_KEY = "infd_image_engine";
const CLOUD_PROVIDER_KEY = "infd_cloud_provider";

export interface EnginePreference {
  mode: EngineMode;
  cloudProvider: CloudProvider;
}

const DEFAULT_PREFERENCE: EnginePreference = {
  mode: "auto",
  cloudProvider: "openai",
};

export function loadEnginePreference(): EnginePreference {
  if (typeof window === "undefined") return DEFAULT_PREFERENCE;
  const mode = window.sessionStorage.getItem(STORAGE_KEY);
  const cloudProvider = window.sessionStorage.getItem(CLOUD_PROVIDER_KEY);
  return {
    mode: isEngineMode(mode) ? mode : "auto",
    cloudProvider: isCloudProvider(cloudProvider) ? cloudProvider : "openai",
  };
}

export function saveEnginePreference(preference: EnginePreference): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(STORAGE_KEY, preference.mode);
  window.sessionStorage.setItem(CLOUD_PROVIDER_KEY, preference.cloudProvider);
}

export function resolveImageBackend(
  preference: EnginePreference,
  capabilities: CapabilitiesResponse | null,
): ImageBackend {
  if (preference.mode === "auto") return "auto";
  if (preference.mode === "local") return "local";

  const available = cloudBackends(capabilities);
  if (available.includes(preference.cloudProvider)) {
    return preference.cloudProvider;
  }
  if (available.length > 0) {
    return available[0];
  }
  return preference.cloudProvider;
}

export function cloudBackends(
  capabilities: CapabilitiesResponse | null,
): CloudProvider[] {
  if (!capabilities) return [];
  const fromFeature = capabilities.features.txt2img?.available_backends ?? [];
  const result: CloudProvider[] = [];
  if (fromFeature.includes("openai") || capabilities.services.openai_images?.ok) {
    result.push("openai");
  }
  if (fromFeature.includes("dashscope") || capabilities.services.dashscope?.ok) {
    result.push("dashscope");
  }
  return result;
}

export function hasLocalImageBackend(
  capabilities: CapabilitiesResponse | null,
): boolean {
  if (!capabilities) return true;
  const backends = capabilities.features.txt2img?.available_backends ?? [];
  return backends.some((b) => b === "sd15" || b === "flux");
}

export function backendDisplayLabel(backend: string | null | undefined): string {
  switch (backend) {
    case "openai":
      return "OpenAI Images";
    case "dashscope":
    case "dashscope_api":
      return "万相 DashScope";
    case "flux":
      return "Flux";
    case "sd15":
    case "local":
      return "本地 SD 1.5";
    default:
      return backend ? backend : "自动";
  }
}

function isEngineMode(value: string | null): value is EngineMode {
  return value === "auto" || value === "local" || value === "cloud";
}

function isCloudProvider(value: string | null): value is CloudProvider {
  return value === "openai" || value === "dashscope";
}
