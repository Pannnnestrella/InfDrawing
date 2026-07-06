import { createMessageId } from "@/agent-panel/types";
import { pasteImageUrlToCanvas } from "@/lib/canvas-bridge";

import type { FlowCallbacks } from "./flow-types";

/** Append preview message and paste generated image onto the canvas. */
export async function completeWithCanvasPaste(
  imageUrl: string,
  callbacks: Pick<FlowCallbacks, "appendMessage" | "appendStatus" | "appendError">,
  caption?: string,
): Promise<void> {
  callbacks.appendMessage({
    id: createMessageId(),
    role: "assistant",
    kind: "image",
    imageUrl,
    caption,
  });
  try {
    const pasted = await pasteImageUrlToCanvas(imageUrl);
    if (!pasted) {
      callbacks.appendError("生成成功，但画布未就绪（结果仍可在上方预览）");
    } else {
      callbacks.appendStatus("已回贴到画布");
    }
  } catch (err) {
    callbacks.appendError(
      err instanceof Error ? `回贴画布失败：${err.message}` : "回贴画布失败",
    );
  }
}
