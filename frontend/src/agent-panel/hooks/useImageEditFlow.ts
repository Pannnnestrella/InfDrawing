import { submitImageEdit } from "@/lib/api";
import { exportSelectedImageFile } from "@/lib/canvas-bridge";

import { completeWithCanvasPaste } from "./complete-generation";
import type { FlowCallbacks } from "./flow-types";
import { useGenerateFlow } from "./useGenerateFlow";

export function useImageEditFlow(callbacks: FlowCallbacks) {
  return useGenerateFlow(callbacks, {
    submittedStatus: "指令改图任务已提交…",
    runningStatus: "OpenAI 改图进行中…",
    submit: async (prompt) => {
      const image = await exportSelectedImageFile();
      if (!image) {
        throw new Error("指令改图需要选中一张画布图片");
      }
      return submitImageEdit({ image, prompt });
    },
    complete: (result, _input, cb) => completeWithCanvasPaste(result.imageUrl, cb),
  });
}
