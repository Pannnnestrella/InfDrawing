import { submitInpaint } from "@/lib/api";
import { getCanvasMaskPair } from "@/lib/canvas-bridge";
import type { ImageBackend } from "@/lib/engine-preference";

import { completeWithCanvasPaste } from "./complete-generation";
import type { FlowCallbacks } from "./flow-types";
import { useGenerateFlow } from "./useGenerateFlow";

export interface InpaintFlowInput {
  imageFile: File | null;
  maskFile: File | null;
}

export function useInpaintFlow(
  callbacks: FlowCallbacks,
  getBackend: () => ImageBackend,
) {
  return useGenerateFlow<InpaintFlowInput>(callbacks, {
    submittedStatus: "局部重绘任务已提交…",
    runningStatus: "局部重绘进行中…",
    submit: (prompt, files) => {
      const canvasPair = getCanvasMaskPair();
      const image = canvasPair?.image ?? files.imageFile;
      const mask = canvasPair?.mask ?? files.maskFile;
      if (!image || !mask) {
        throw new Error("局部重绘需要原图和 Mask：选中图片后刷选 Mask");
      }
      return submitInpaint({ image, mask, prompt, backend: getBackend() });
    },
    complete: (result, _input, cb) => completeWithCanvasPaste(result.imageUrl, cb),
  });
}
