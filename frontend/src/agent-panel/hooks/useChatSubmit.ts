import { useCallback } from "react";

import {
  createMessageId,
  MODE_LABELS,
  type ChatMode,
} from "@/agent-panel/types";
import { getCanvasContextSnapshot } from "@/lib/canvas-bridge";
import { requestPlan, type TextRegion } from "@/lib/api";

import type { FlowCallbacks } from "./flow-types";
import type { InpaintFlowInput } from "./useInpaintFlow";

const DECOMPOSE_DEFAULT_PROMPT = "clean seamless background, high quality";

export interface ChatSubmitFlows {
  txt2img: { execute: (refinedPrompt: string) => Promise<void> };
  inpaint: { execute: (refinedPrompt: string, files: InpaintFlowInput) => Promise<void> };
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
  selectedTextIndex: number | null;
  textRegions: TextRegion[];
  inpaintFiles: InpaintFlowInput;
  flows: ChatSubmitFlows;
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
    selectedTextIndex,
    textRegions,
    inpaintFiles,
    flows,
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
      const plan = await requestPlan({
        user_message: userText,
        intent_override: mode,
        context: getCanvasContextSnapshot(),
      });
      callbacks.appendStatus(`${MODE_LABELS[mode]} · ${plan.refined_prompt}`);

      if (plan.intent === "txt2img") {
        await flows.txt2img.execute(plan.refined_prompt);
        return;
      }

      if (plan.intent === "inpaint") {
        await flows.inpaint.execute(plan.refined_prompt, inpaintFiles);
        return;
      }

      if (plan.intent === "decompose") {
        await flows.decompose.execute(plan.refined_prompt);
        return;
      }

      if (plan.intent === "text_edit") {
        const region =
          selectedTextIndex !== null ? textRegions[selectedTextIndex] : undefined;
        if (!region) {
          callbacks.appendError("请选择要替换的文字块");
          setBusy(false);
          return;
        }
        await flows.text_edit.execute(plan.refined_prompt, { region });
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
    selectedTextIndex,
    textRegions,
    inpaintFiles,
    flows,
    callbacks,
  ]);

  return { handleSubmit };
}
