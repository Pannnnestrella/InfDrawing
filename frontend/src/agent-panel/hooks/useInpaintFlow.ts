import { useCallback } from "react";

import { getCanvasMaskPair } from "@/lib/canvas-bridge";
import { submitInpaint } from "@/lib/api";
import { runGenerateTask } from "@/lib/generate-task";

import { completeWithCanvasPaste } from "./complete-generation";
import type { FlowCallbacks } from "./flow-types";

export interface InpaintFlowInput {
  imageFile: File | null;
  maskFile: File | null;
}

export function useInpaintFlow(callbacks: FlowCallbacks) {
  const { appendStatus, appendError, notifyReconnect, setBusy } = callbacks;

  const execute = useCallback(
    async (refinedPrompt: string, files: InpaintFlowInput) => {
      const canvasPair = getCanvasMaskPair();
      const resolvedImage = canvasPair?.image ?? files.imageFile;
      const resolvedMask = canvasPair?.mask ?? files.maskFile;

      if (!resolvedImage || !resolvedMask) {
        appendError("局部重绘需要原图和 Mask：选中图片后刷选 Mask");
        setBusy(false);
        return;
      }

      appendStatus("局部重绘任务已提交…");
      const { task_id } = await submitInpaint({
        image: resolvedImage,
        mask: resolvedMask,
        prompt: refinedPrompt,
      });
      runGenerateTask(task_id, {
        onProgress: () => appendStatus("局部重绘进行中…"),
        onReconnect: notifyReconnect,
        onComplete: async (url) => {
          await completeWithCanvasPaste(url, callbacks);
          setBusy(false);
        },
        onError: (msg) => {
          appendError(msg);
          setBusy(false);
        },
      });
    },
    [callbacks, appendStatus, appendError, notifyReconnect, setBusy],
  );

  return { execute };
}
