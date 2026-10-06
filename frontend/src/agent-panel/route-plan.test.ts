import { describe, expect, it } from "vitest";

import type { IntentPlan } from "@/lib/api";
import type { CapabilitiesResponse } from "@/lib/capabilities";

import {
  evaluatePlan,
  getClarificationMessage,
  getIntentOverride,
  validateIntentAvailability,
  validateIntentRequirements,
  type IntentExecutionContext,
} from "./route-plan";

const READY_CONTEXT: IntentExecutionContext = {
  hasSelectedImage: true,
  hasMask: true,
  selectedTextIndex: 0,
  textRegionCount: 1,
  ocrLoading: false,
  ocrError: null,
};

describe("getIntentOverride", () => {
  it("omits the override in automatic mode", () => {
    expect(getIntentOverride("auto")).toBeUndefined();
  });

  it.each(["txt2img", "inpaint", "decompose", "text_edit"] as const)(
    "keeps the %s manual override",
    (mode) => {
      expect(getIntentOverride(mode)).toBe(mode);
    },
  );
});

function createPlan(overrides: Partial<IntentPlan> = {}): IntentPlan {
  return {
    intent: "txt2img",
    refined_prompt: "a red apple",
    negative_prompt: "",
    target_tool: "comfyui_txt2img_v1",
    params: {},
    confidence: 1,
    ...overrides,
  };
}

describe("getClarificationMessage", () => {
  it("reads the current backend clarification contract", () => {
    const plan = createPlan({
      clarification_required: true,
      clarification_question: "请先选择目标图片。",
    });

    expect(getClarificationMessage(plan)).toBe("请先选择目标图片。");
  });

  it("returns the backend clarification and stops executable routing", () => {
    const plan = createPlan({
      needs_clarification: true,
      clarification_message: "你希望修改哪张图片？",
    });

    expect(getClarificationMessage(plan)).toBe("你希望修改哪张图片？");
  });

  it("ignores a clarification message when the plan is executable", () => {
    expect(
      getClarificationMessage(
        createPlan({ clarification_message: "unused", needs_clarification: false }),
      ),
    ).toBeNull();
  });
});

describe("validateIntentRequirements", () => {
  it.each(["inpaint", "decompose", "text_edit"] as const)(
    "requires an image selection for %s",
    (intent) => {
      expect(
        validateIntentRequirements(intent, {
          ...READY_CONTEXT,
          hasSelectedImage: false,
        }),
      ).toContain("选中一张图片");
    },
  );

  it("requires a mask for inpaint", () => {
    expect(
      validateIntentRequirements("inpaint", {
        ...READY_CONTEXT,
        hasMask: false,
      }),
    ).toContain("Mask");
  });

  it("requires a selected OCR region for text editing", () => {
    expect(
      validateIntentRequirements("text_edit", {
        ...READY_CONTEXT,
        selectedTextIndex: null,
      }),
    ).toContain("文字块");
  });

  it("allows executable inputs for every intent", () => {
    for (const intent of [
      "txt2img",
      "inpaint",
      "image_edit",
      "decompose",
      "text_edit",
    ] as const) {
      expect(validateIntentRequirements(intent, READY_CONTEXT)).toBeNull();
    }
  });

  it("requires a selected image for image_edit but not a mask", () => {
    expect(
      validateIntentRequirements("image_edit", {
        ...READY_CONTEXT,
        hasSelectedImage: false,
      }),
    ).toContain("选中一张图片");
    expect(
      validateIntentRequirements("image_edit", {
        ...READY_CONTEXT,
        hasMask: false,
      }),
    ).toBeNull();
  });
});

describe("validateIntentAvailability", () => {
  it("blocks an intent disabled by backend capabilities", () => {
    const capabilities = {
      tier: "cpu_only",
      gpu: { available: false },
      services: {
        ollama: { ok: true, url: "" },
        comfyui: { ok: false, url: "" },
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
        inpaint: { enabled: false, reason: "缺少 inpaint 模型" },
      },
    } satisfies CapabilitiesResponse;

    expect(validateIntentAvailability("inpaint", capabilities)).toBe(
      "缺少 inpaint 模型",
    );
  });
});

describe("evaluatePlan", () => {
  it.each(["txt2img", "inpaint", "image_edit", "decompose", "text_edit"] as const)(
    "routes an executable %s plan to its matching flow",
    (intent) => {
      expect(evaluatePlan(createPlan({ intent }), null, READY_CONTEXT)).toEqual({
        kind: "execute",
        intent,
        refinedPrompt: "a red apple",
      });
    },
  );

  it("returns clarification before any execution decision", () => {
    expect(
      evaluatePlan(
        createPlan({
          intent: "inpaint",
          needs_clarification: true,
          clarification_message: "需要修改哪个区域？",
        }),
        null,
        { ...READY_CONTEXT, hasMask: false },
      ),
    ).toEqual({
      kind: "clarification",
      message: "需要修改哪个区域？",
    });
  });
});
