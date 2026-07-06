import { useEffect, useState } from "react";

import {
  getCanvasContextSnapshot,
  getCanvasEditor,
  getCanvasSelectionHint,
  subscribeCanvasBridge,
} from "@/lib/canvas-bridge";

export function useCanvasSync() {
  const [canvasReady, setCanvasReady] = useState(false);
  const [canvasHasSelection, setCanvasHasSelection] = useState(false);
  const [canvasHasMask, setCanvasHasMask] = useState(false);
  const [selectionHint, setSelectionHint] = useState<string | null>("画布加载中…");
  const [selectedShapeId, setSelectedShapeId] = useState<string | null>(null);

  useEffect(() => {
    const sync = () => {
      setCanvasReady(getCanvasEditor() !== null);
      const ctx = getCanvasContextSnapshot();
      setCanvasHasSelection(ctx.selectedShapeId !== null);
      setCanvasHasMask(ctx.hasMask);
      setSelectionHint(getCanvasSelectionHint());
      setSelectedShapeId(ctx.selectedShapeId);
    };
    sync();
    const unsub = subscribeCanvasBridge(sync);
    const timer = window.setInterval(sync, 400);
    return () => {
      unsub();
      window.clearInterval(timer);
    };
  }, []);

  return {
    canvasReady,
    canvasHasSelection,
    canvasHasMask,
    selectionHint,
    selectedShapeId,
  };
}
