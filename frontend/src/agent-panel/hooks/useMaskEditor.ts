import { useCallback, useState } from "react";

import {
  exportSelectedImageForInpaint,
  getSelectedImagePreviewUrl,
  setCanvasMaskPair,
} from "@/lib/canvas-bridge";

import type { FlowCallbacks } from "./flow-types";

export function useMaskEditor(
  callbacks: Pick<FlowCallbacks, "appendStatus" | "appendError">,
) {
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [maskFile, setMaskFile] = useState<File | null>(null);
  const [maskEditorOpen, setMaskEditorOpen] = useState(false);
  const [maskPreviewUrl, setMaskPreviewUrl] = useState<string | null>(null);

  const openMaskEditor = useCallback(async () => {
    const url = await getSelectedImagePreviewUrl();
    if (!url) {
      callbacks.appendError("请先在画布上选中一张图片");
      return;
    }
    setMaskPreviewUrl(url);
    setMaskEditorOpen(true);
  }, [callbacks]);

  const closeMaskEditor = useCallback(() => {
    setMaskEditorOpen(false);
    setMaskPreviewUrl(null);
  }, []);

  const handleMaskComplete = useCallback(
    async (mask: File) => {
      try {
        const image = await exportSelectedImageForInpaint();
        if (!image) {
          callbacks.appendError("无法导出选中图片");
          return;
        }
        setCanvasMaskPair({ image, mask });
        setImageFile(image);
        setMaskFile(mask);
        setMaskEditorOpen(false);
        setMaskPreviewUrl(null);
        callbacks.appendStatus("Mask 已就绪，可以发送局部重绘指令");
      } catch (err) {
        callbacks.appendError(err instanceof Error ? err.message : "Mask 导出失败");
      }
    },
    [callbacks],
  );

  return {
    imageFile,
    maskFile,
    maskEditorOpen,
    maskPreviewUrl,
    openMaskEditor,
    closeMaskEditor,
    handleMaskComplete,
  };
}
