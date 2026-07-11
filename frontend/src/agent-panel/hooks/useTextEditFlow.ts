import { createMessageId } from "@/agent-panel/types";
import { submitTextEdit, type TextRegion } from "@/lib/api";
import {
  exportSelectedImageFile,
  overlayTextOnSelectedImage,
  replaceSelectedImageSrc,
} from "@/lib/canvas-bridge";

import type { FlowCallbacks } from "./flow-types";
import { useGenerateFlow } from "./useGenerateFlow";

export interface TextEditFlowInput {
  region: TextRegion;
}

export function useTextEditFlow(callbacks: FlowCallbacks) {
  return useGenerateFlow<TextEditFlowInput>(callbacks, {
    submittedStatus: "文字编辑任务已提交…",
    runningStatus: "文字编辑进行中…",
    stepLabels: { inpainting: "抹除原字中…" },
    submit: async (newText, { region }) => {
      const imageFile = await exportSelectedImageFile();
      if (!imageFile) {
        throw new Error("无法导出选中图片");
      }
      return submitTextEdit({ image: imageFile, bbox: region.bbox, newText });
    },
    complete: async (result, { region }, cb) => {
      const replaced = await replaceSelectedImageSrc(result.imageUrl);
      if (!replaced) {
        throw new Error("抹字成功，但更新画布图片失败");
      }
      const overlay = result.overlay;
      if (overlay) {
        const overlaid = overlayTextOnSelectedImage(overlay.text, overlay.bbox, {
          width: overlay.image_width,
          height: overlay.image_height,
        });
        if (!overlaid) {
          cb.appendError("抹字成功，但叠字失败");
        } else {
          cb.appendStatus(`已将「${region.text}」替换为「${overlay.text}」`);
        }
      }
      cb.appendMessage({
        id: createMessageId(),
        role: "assistant",
        kind: "image",
        imageUrl: result.imageUrl,
        caption: "文字编辑结果",
      });
    },
  });
}
