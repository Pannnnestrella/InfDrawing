import { useCallback } from "react";

import {
  exportSelectedImageFile,
  getSelectedImageAnchor,
  pasteLayersToCanvas,
} from "@/lib/canvas-bridge";
import { submitDecompose } from "@/lib/api";
import { runGenerateTask } from "@/lib/generate-task";

import type { FlowCallbacks } from "./flow-types";

const STEP_LABELS: Record<string, string> = {
  segmenting: "分割主体…",
  extracting: "提取前景…",
  inpainting: "补全背景…",
};

export function useDecomposeFlow(callbacks: FlowCallbacks) {
  const { appendStatus, appendError, notifyReconnect, setBusy } = callbacks;

  const execute = useCallback(
    async (refinedPrompt: string) => {
      const anchor = getSelectedImageAnchor();
      if (!anchor) {
        appendError("元素拆解需要先在画布上选中一张图片");
        setBusy(false);
        return;
      }

      const imageFile = await exportSelectedImageFile();
      if (!imageFile) {
        appendError("无法导出选中图片");
        setBusy(false);
        return;
      }

      appendStatus("元素拆解任务已提交…");
      const { task_id } = await submitDecompose(imageFile, refinedPrompt);
      runGenerateTask(task_id, {
        onProgress: (step) => {
          appendStatus(STEP_LABELS[step ?? ""] ?? "元素拆解进行中…");
        },
        onReconnect: notifyReconnect,
        onComplete: async (_url, layers) => {
          try {
            if (!layers?.length) {
              appendError("未收到图层数据");
              setBusy(false);
              return;
            }
            const pasted = await pasteLayersToCanvas(layers, anchor);
            if (!pasted) {
              appendError("拆解成功，但回贴画布失败");
            } else {
              appendStatus(`已回贴 ${layers.length} 个图层到画布`);
            }
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
    [appendStatus, appendError, notifyReconnect, setBusy],
  );

  return { execute };
}
