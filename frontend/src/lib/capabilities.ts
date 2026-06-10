import { API_BASE } from "./theme";

export interface GpuInfo {
  available: boolean;
  name?: string | null;
  vram_total_mb?: number | null;
  vram_free_mb?: number | null;
}

export interface ServiceStatus {
  ok: boolean;
  url: string;
  remote?: boolean;
}

export interface ModelsCapability {
  sd15_txt2img: boolean;
  sd15_inpaint: boolean;
  flux_txt2img: boolean;
  sam2_segment: boolean;
  flux_fill: boolean;
  anytext2: boolean;
}

export interface FeatureCapability {
  enabled: boolean;
  backend?: string | null;
  reason?: string | null;
}

export interface CapabilitiesResponse {
  tier: string;
  gpu: GpuInfo;
  services: {
    ollama: ServiceStatus;
    comfyui: ServiceStatus;
  };
  models: ModelsCapability;
  features: Record<string, FeatureCapability>;
}

const TIER_LABELS: Record<string, string> = {
  cpu_only: "CPU / 无 ComfyUI",
  local_8gb: "本机 8GB",
  gpu_24gb: "云 GPU 24GB",
  gpu_48gb: "云 GPU 48GB",
  api_fallback: "API Fallback",
};

export function tierLabel(tier: string): string {
  return TIER_LABELS[tier] ?? tier;
}

export async function fetchCapabilities(): Promise<CapabilitiesResponse> {
  const response = await fetch(`${API_BASE}/api/v1/system/capabilities`);
  if (!response.ok) {
    throw new Error(`capabilities failed: ${response.status}`);
  }
  return (await response.json()) as CapabilitiesResponse;
}

export function isModeEnabled(
  capabilities: CapabilitiesResponse | null,
  mode: "txt2img" | "inpaint" | "decompose" | "text_edit",
): boolean {
  if (!capabilities) return true;
  const key =
    mode === "txt2img"
      ? "txt2img"
      : mode === "inpaint"
        ? "inpaint"
        : mode === "decompose"
          ? "decompose"
          : "text_edit";
  return capabilities.features[key]?.enabled ?? false;
}

/** @deprecated Use isModeEnabled */
export function isIntentEnabled(
  capabilities: CapabilitiesResponse | null,
  intent: "txt2img" | "inpaint",
): boolean {
  return isModeEnabled(capabilities, intent);
}

export function featureReason(
  capabilities: CapabilitiesResponse | null,
  key: string,
): string | null {
  if (!capabilities) return null;
  const feature = capabilities.features[key];
  if (!feature || feature.enabled) return null;
  return feature.reason ?? "当前环境不可用";
}
