import { describe, expect, it } from "vitest";

import type { CapabilitiesResponse } from "@/lib/capabilities";
import {
  cloudBackends,
  resolveImageBackend,
  type EnginePreference,
} from "@/lib/engine-preference";

function caps(available: string[]): CapabilitiesResponse {
  return {
    tier: "api_fallback",
    gpu: { available: false },
    services: {
      ollama: { ok: true, url: "" },
      comfyui: { ok: false, url: "" },
      openai_images: { ok: available.includes("openai"), url: "" },
      dashscope: { ok: available.includes("dashscope"), url: "" },
    },
    models: {
      sd15_txt2img: false,
      sd15_inpaint: false,
      flux_txt2img: false,
      sam2_segment: false,
      flux_fill: false,
      anytext2: false,
    },
    features: {
      txt2img: {
        enabled: available.length > 0,
        backend: available[0] ?? null,
        available_backends: available,
      },
    },
  };
}

describe("resolveImageBackend", () => {
  it("keeps auto and local as API values", () => {
    const preference: EnginePreference = { mode: "auto", cloudProvider: "openai" };
    expect(resolveImageBackend(preference, caps(["sd15", "openai"]))).toBe("auto");
    expect(
      resolveImageBackend(
        { mode: "local", cloudProvider: "openai" },
        caps(["sd15", "openai"]),
      ),
    ).toBe("local");
  });

  it("maps cloud mode to the selected provider", () => {
    expect(
      resolveImageBackend(
        { mode: "cloud", cloudProvider: "dashscope" },
        caps(["openai", "dashscope"]),
      ),
    ).toBe("dashscope");
  });

  it("falls back to the first available cloud provider", () => {
    expect(
      resolveImageBackend(
        { mode: "cloud", cloudProvider: "openai" },
        caps(["dashscope"]),
      ),
    ).toBe("dashscope");
  });
});

describe("cloudBackends", () => {
  it("reads available cloud backends from capabilities", () => {
    expect(cloudBackends(caps(["sd15", "openai", "dashscope"]))).toEqual([
      "openai",
      "dashscope",
    ]);
  });
});
