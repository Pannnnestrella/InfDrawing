import { useCallback, useEffect, useRef, useState } from "react";

import type { ChatMode } from "@/agent-panel/types";
import { exportSelectedImageFile } from "@/lib/canvas-bridge";
import { detectTextRegions, type TextRegion } from "@/lib/api";

export function useTextEditOcr(mode: ChatMode, selectedShapeId: string | null) {
  const [textRegions, setTextRegions] = useState<TextRegion[]>([]);
  const [selectedTextIndex, setSelectedTextIndex] = useState<number | null>(null);
  const [ocrLoading, setOcrLoading] = useState(false);
  const [ocrError, setOcrError] = useState<string | null>(null);
  const lastOcrShapeRef = useRef<string | null>(null);

  const runOcr = useCallback(async () => {
    setOcrLoading(true);
    setOcrError(null);
    setTextRegions([]);
    setSelectedTextIndex(null);
    try {
      const file = await exportSelectedImageFile();
      if (!file) {
        setOcrError("无法导出选中图片");
        return;
      }
      const result = await detectTextRegions(file);
      setTextRegions(result.regions);
      if (result.regions.length > 0) {
        setSelectedTextIndex(0);
      }
    } catch (err) {
      setOcrError(err instanceof Error ? err.message : "OCR 检测失败");
    } finally {
      setOcrLoading(false);
    }
  }, []);

  useEffect(() => {
    if (mode !== "text_edit") {
      lastOcrShapeRef.current = null;
      return;
    }
    if (!selectedShapeId) return;
    if (lastOcrShapeRef.current === selectedShapeId) return;
    lastOcrShapeRef.current = selectedShapeId;
    void runOcr();
  }, [mode, selectedShapeId, runOcr]);

  const retryOcr = useCallback(() => {
    lastOcrShapeRef.current = null;
    void runOcr();
  }, [runOcr]);

  return {
    textRegions,
    selectedTextIndex,
    setSelectedTextIndex,
    ocrLoading,
    ocrError,
    retryOcr,
  };
}
