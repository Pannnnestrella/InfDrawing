import type { IntentType } from "./api-types";
import { API_BASE } from "./config";

/** Feature keys shared with the backend; chat modes map onto them 1:1. */
export type FeatureKey = IntentType;

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
  mode: FeatureKey,
): boolean {
  if (!capabilities) return true;
  return capabilities.features[mode]?.enabled ?? false;
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
