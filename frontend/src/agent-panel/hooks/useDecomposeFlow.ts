import { useRef } from "react";

import { getSelectedImageAnchor } from "@/lib/canvas-bridge";
import { pasteDecomposeResult, submitDecomposeFromSelection } from "@/lib/run-pipeline";

import type { FlowCallbacks } from "./flow-types";
import { useGenerateFlow } from "./useGenerateFlow";

export function useDecomposeFlow(callbacks: FlowCallbacks) {
  const anchorRef = useRef<{ pageX: number; pageY: number } | null>(null);

  return useGenerateFlow(callbacks, {
    submittedStatus: "元素拆解任务已提交…",
    runningStatus: "元素拆解进行中…",
    submit: (prompt) => {
      const anchor = getSelectedImageAnchor();
      if (!anchor) {
        throw new Error("元素拆解需要先在画布上选中一张图片");
      }
      anchorRef.current = anchor;
      return submitDecomposeFromSelection(prompt);
    },
    complete: async (result, _input, cb) => {
      const count = await pasteDecomposeResult(result, anchorRef.current!);
      cb.appendStatus(`已回贴 ${count} 个图层到画布`);
    },
  });
}
