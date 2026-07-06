import { useCallback } from "react";

import { submitTxt2Img } from "@/lib/api";
import { runGenerateTask } from "@/lib/generate-task";

import { completeWithCanvasPaste } from "./complete-generation";
import type { FlowCallbacks } from "./flow-types";

export function useTxt2ImgFlow(callbacks: FlowCallbacks) {
  const { appendStatus, appendError, notifyReconnect, setBusy } = callbacks;

  const execute = useCallback(
    async (refinedPrompt: string) => {
      appendStatus("生图任务已提交…");
      const { task_id } = await submitTxt2Img(refinedPrompt, "auto");
      runGenerateTask(task_id, {
        onProgress: () => appendStatus("生图进行中…"),
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
