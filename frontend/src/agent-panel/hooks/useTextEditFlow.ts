import { useCallback } from "react";

import { createMessageId } from "@/agent-panel/types";
import {
  exportSelectedImageFile,
  overlayTextOnSelectedImage,
  replaceSelectedImageSrc,
} from "@/lib/canvas-bridge";
import { submitTextEdit, type TextRegion } from "@/lib/api";
import { runGenerateTask } from "@/lib/generate-task";

import type { FlowCallbacks } from "./flow-types";

export interface TextEditFlowInput {
  region: TextRegion;
}

export function useTextEditFlow(callbacks: FlowCallbacks) {
  const { appendMessage, appendStatus, appendError, notifyReconnect, setBusy } = callbacks;

  const execute = useCallback(
    async (refinedPrompt: string, input: TextEditFlowInput) => {
      const { region } = input;

      const imageFile = await exportSelectedImageFile();
      if (!imageFile) {
        appendError("无法导出选中图片");
        setBusy(false);
        return;
      }

      appendStatus("文字编辑任务已提交…");
      const { task_id } = await submitTextEdit({
        image: imageFile,
        bbox: region.bbox,
        newText: refinedPrompt,
      });
      runGenerateTask(task_id, {
        onProgress: (step) => {
          appendStatus(step === "inpainting" ? "抹除原字中…" : "准备文字区域…");
        },
        onReconnect: notifyReconnect,
        onComplete: async (url, _layers, overlay) => {
          try {
            const replaced = await replaceSelectedImageSrc(url);
            if (!replaced) {
              appendError("抹字成功，但更新画布图片失败");
              setBusy(false);
              return;
            }
            if (overlay) {
              const overlaid = overlayTextOnSelectedImage(overlay.text, overlay.bbox, {
                width: overlay.image_width,
                height: overlay.image_height,
              });
              if (!overlaid) {
                appendError("抹字成功，但叠字失败");
              } else {
                appendStatus(`已将「${region.text}」替换为「${overlay.text}」`);
              }
            }
            appendMessage({
              id: createMessageId(),
              role: "assistant",
              kind: "image",
              imageUrl: url,
              caption: "文字编辑结果",
            });
          } catch (err) {
            appendError(err instanceof Error ? err.message : "回贴失败");
          }
          setBusy(false);
        },
        onError: (msg) => {
          appendError(msg);
          setBusy(false);
        },
      });
    },
    [appendMessage, appendStatus, appendError, notifyReconnect, setBusy],
  );

  return { execute };
}
