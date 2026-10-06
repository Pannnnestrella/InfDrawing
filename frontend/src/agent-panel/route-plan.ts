import type { IntentPlan, IntentType } from "@/lib/api";
import {
  featureReason,
  isModeEnabled,
  type CapabilitiesResponse,
} from "@/lib/capabilities";

import type { ChatMode } from "./types";

export interface IntentExecutionContext {
  hasSelectedImage: boolean;
  hasMask: boolean;
  selectedTextIndex: number | null;
  textRegionCount: number;
  ocrLoading: boolean;
  ocrError: string | null;
}

export type PlanDecision =
  | { kind: "clarification"; message: string }
  | { kind: "error"; message: string }
  | { kind: "execute"; intent: IntentType; refinedPrompt: string };

export function getIntentOverride(mode: ChatMode): IntentType | undefined {
  return mode === "auto" ? undefined : mode;
}

export function getClarificationMessage(plan: IntentPlan): string | null {
  if (!plan.clarification_required && !plan.needs_clarification) return null;
  return (
    plan.clarification_question?.trim() ||
    plan.clarification_message?.trim() ||
    "请补充更多信息后再试。"
  );
}

export function validateIntentAvailability(
  intent: IntentType,
  capabilities: CapabilitiesResponse | null,
): string | null {
  if (isModeEnabled(capabilities, intent)) return null;
  return featureReason(capabilities, intent) ?? "当前环境不支持此功能";
}

export function validateIntentRequirements(
  intent: IntentType,
  context: IntentExecutionContext,
): string | null {
  if (intent === "txt2img") return null;

  if (!context.hasSelectedImage) {
    return "请先在画布上选中一张图片";
  }

  if (intent === "inpaint") {
    return context.hasMask ? null : "局部重绘需要先为选中图片刷选 Mask";
  }

  if (intent === "image_edit" || intent === "decompose") return null;

  if (intent === "text_edit") {
    if (context.ocrLoading) return "正在识别图片文字，请稍后再发送";
    if (context.ocrError) return `文字识别失败：${context.ocrError}`;
    if (context.textRegionCount === 0) return "选中图片中未检测到可编辑文字";
    if (
      context.selectedTextIndex === null ||
      context.selectedTextIndex < 0 ||
      context.selectedTextIndex >= context.textRegionCount
    ) {
      return "请先选择要替换的文字块";
    }
    return null;
  }

  return null;
}

export function evaluatePlan(
  plan: IntentPlan,
  capabilities: CapabilitiesResponse | null,
  context: IntentExecutionContext,
): PlanDecision {
  const clarification = getClarificationMessage(plan);
  if (clarification) {
    return { kind: "clarification", message: clarification };
  }

  const validationError =
    validateIntentAvailability(plan.intent, capabilities) ??
    validateIntentRequirements(plan.intent, context);
  if (validationError) {
    return { kind: "error", message: validationError };
  }

  return {
    kind: "execute",
    intent: plan.intent,
    refinedPrompt: plan.refined_prompt,
  };
}
