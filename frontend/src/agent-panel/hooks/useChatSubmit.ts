import { useCallback } from "react";

import {
  createMessageId,
  MODE_LABELS,
  type ChatMode,
} from "@/agent-panel/types";
import { evaluatePlan, getIntentOverride } from "@/agent-panel/route-plan";
import { getCanvasContextSnapshot } from "@/lib/canvas-bridge";
import { requestPlan, type TextRegion } from "@/lib/api";
import type { CapabilitiesResponse } from "@/lib/capabilities";

import type { FlowCallbacks } from "./flow-types";
import type { InpaintFlowInput } from "./useInpaintFlow";

const DECOMPOSE_DEFAULT_PROMPT = "clean seamless background, high quality";

export interface ChatSubmitFlows {
  txt2img: { execute: (refinedPrompt: string) => Promise<void> };
  inpaint: { execute: (refinedPrompt: string, files: InpaintFlowInput) => Promise<void> };
  image_edit: { execute: (refinedPrompt: string) => Promise<void> };
  decompose: { execute: (refinedPrompt: string) => Promise<void> };
  text_edit: {
    execute: (refinedPrompt: string, input: { region: TextRegion }) => Promise<void>;
  };
}

export interface UseChatSubmitOptions {
  mode: ChatMode;
  message: string;
  setMessage: (value: string) => void;
  busy: boolean;
  setBusy: (busy: boolean) => void;
  modeEnabled: boolean;
  modeDisabledReason: string | null;
  capabilities: CapabilitiesResponse | null;
  selectedTextIndex: number | null;
  textRegions: TextRegion[];
  ocrLoading: boolean;
  ocrError: string | null;
  inpaintFiles: InpaintFlowInput;
  flows: ChatSubmitFlows;
  beginSession: (mode: ChatMode, userText: string) => string;
  callbacks: Pick<FlowCallbacks, "appendMessage" | "appendStatus" | "appendError">;
}

export function useChatSubmit(options: UseChatSubmitOptions) {
  const {
    mode,
    message,
    setMessage,
    busy,
    setBusy,
    modeEnabled,
    modeDisabledReason,
    capabilities,
    selectedTextIndex,
    textRegions,
    ocrLoading,
    ocrError,
    inpaintFiles,
    flows,
    beginSession,
    callbacks,
  } = options;

  const handleSubmit = useCallback(async () => {
    const text = message.trim();
    if (mode !== "decompose" && !text) return;
    if (mode === "text_edit" && selectedTextIndex === null) {
      callbacks.appendError("请先选择要替换的文字块");
      return;
    }
    if (!modeEnabled) {
      callbacks.appendError(modeDisabledReason ?? "当前环境不支持此功能");
      return;
    }
    if (busy) return;

    const userText = text || (mode === "decompose" ? DECOMPOSE_DEFAULT_PROMPT : "");
    // One user request → one dedicated session for later switching.
    beginSession(mode, text || userText);
    callbacks.appendMessage({
      id: createMessageId(),
      role: "user",
      mode,
      text: text || (mode === "decompose" ? "（使用默认背景风格）" : userText),
    });
    setMessage("");
    setBusy(true);

    try {
      callbacks.appendStatus("理解意图中…");
      const canvasContext = getCanvasContextSnapshot();
      const selectedRegion =
        selectedTextIndex !== null ? textRegions[selectedTextIndex] : undefined;
      const routingCapabilities = Object.fromEntries(
        Object.entries(capabilities?.features ?? {}).map(([key, feature]) => [
          key,
          feature.enabled,
        ]),
      );
      const plan = await requestPlan({
        user_message: userText,
        intent_override: getIntentOverride(mode),
        context: {
          image_id: canvasContext.selectedShapeId,
          mask_id: canvasContext.hasMask ? "canvas-mask" : null,
          bbox: selectedRegion?.bbox,
          new_text: selectedRegion ? userText : null,
          capabilities: routingCapabilities,
          metadata: {
            image_width: canvasContext.imageWidth,
            image_height: canvasContext.imageHeight,
          },
        },
      });
      const latestCanvasContext = getCanvasContextSnapshot();

      const decision = evaluatePlan(plan, capabilities, {
        hasSelectedImage: latestCanvasContext.selectedShapeId !== null,
        hasMask: latestCanvasContext.hasMask,
        selectedTextIndex,
        textRegionCount: textRegions.length,
        ocrLoading,
        ocrError,
      });

      if (decision.kind === "clarification") {
        callbacks.appendMessage({
          id: createMessageId(),
          role: "assistant",
          kind: "clarification",
          text: decision.message,
        });
        setBusy(false);
        return;
      }

      if (decision.kind === "error") {
        callbacks.appendError(decision.message);
        setBusy(false);
        return;
      }

      callbacks.appendStatus(
        `${MODE_LABELS[decision.intent]} · ${decision.refinedPrompt}`,
      );

      if (decision.intent === "txt2img") {
        await flows.txt2img.execute(decision.refinedPrompt);
        return;
      }

      if (decision.intent === "inpaint") {
        await flows.inpaint.execute(decision.refinedPrompt, inpaintFiles);
        return;
      }

      if (decision.intent === "image_edit") {
        await flows.image_edit.execute(decision.refinedPrompt);
        return;
      }

      if (decision.intent === "decompose") {
        await flows.decompose.execute(decision.refinedPrompt);
        return;
      }

      if (decision.intent === "text_edit") {
        const region =
          selectedTextIndex !== null ? textRegions[selectedTextIndex] : undefined;
        if (!region) {
          callbacks.appendError("请选择要替换的文字块");
          setBusy(false);
          return;
        }
        const routedText = plan.params.new_text;
        const replacementText =
          typeof routedText === "string" && routedText.trim()
            ? routedText.trim()
            : decision.refinedPrompt;
        await flows.text_edit.execute(replacementText, { region });
      }
    } catch (err) {
      callbacks.appendError(err instanceof Error ? err.message : "任务失败");
      setBusy(false);
    }
  }, [
    mode,
    message,
    setMessage,
    busy,
    setBusy,
    modeEnabled,
    modeDisabledReason,
    capabilities,
    selectedTextIndex,
    textRegions,
    ocrLoading,
    ocrError,
    inpaintFiles,
    flows,
    beginSession,
    callbacks,
  ]);

  return { handleSubmit };
}
