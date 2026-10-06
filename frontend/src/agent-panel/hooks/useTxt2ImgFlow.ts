import { submitTxt2Img } from "@/lib/api";
import type { ImageBackend } from "@/lib/engine-preference";

import { completeWithCanvasPaste } from "./complete-generation";
import type { FlowCallbacks } from "./flow-types";
import { useGenerateFlow } from "./useGenerateFlow";

export function useTxt2ImgFlow(
  callbacks: FlowCallbacks,
  getBackend: () => ImageBackend,
) {
  return useGenerateFlow(callbacks, {
    submittedStatus: "生图任务已提交…",
    runningStatus: "生图进行中…",
    submit: (prompt) => submitTxt2Img(prompt, getBackend()),
    complete: (result, _input, cb) => completeWithCanvasPaste(result.imageUrl, cb),
  });
}
