import { useEffect, useRef, useState } from "react";

import type { SelectedImageChip } from "@/canvas/types";
import {
  getCanvasContextSnapshot,
  getCanvasEditor,
  getCanvasSelectionHint,
  getSelectedImageChip,
  resolveSelectedImageThumb,
  subscribeCanvasBridge,
} from "@/lib/canvas-bridge";

export function useCanvasSync() {
  const [canvasReady, setCanvasReady] = useState(false);
  const [canvasHasSelection, setCanvasHasSelection] = useState(false);
  const [canvasHasMask, setCanvasHasMask] = useState(false);
  const [selectionHint, setSelectionHint] = useState<string | null>("画布加载中…");
  const [selectedShapeId, setSelectedShapeId] = useState<string | null>(null);
  const [selectedImage, setSelectedImage] = useState<SelectedImageChip | null>(null);
  const resolvedThumbs = useRef(new Map<string, string>());
  const thumbAttempts = useRef(new Set<string>());

  useEffect(() => {
    const sync = () => {
      setCanvasReady(getCanvasEditor() !== null);
      const ctx = getCanvasContextSnapshot();
      setCanvasHasSelection(ctx.selectedShapeId !== null);
      setCanvasHasMask(ctx.hasMask);
      setSelectionHint(getCanvasSelectionHint());
      setSelectedShapeId(ctx.selectedShapeId);

      const chip = getSelectedImageChip();
      if (chip && !chip.thumbSrc) {
        const cached = resolvedThumbs.current.get(chip.id);
        if (cached) chip.thumbSrc = cached;
      }
      setSelectedImage(chip);
      if (!chip || chip.thumbSrc || thumbAttempts.current.has(chip.id)) return;
      thumbAttempts.current.add(chip.id);
      const shapeId = chip.id;
      void resolveSelectedImageThumb(shapeId).then((thumbSrc) => {
        if (!thumbSrc) return;
        resolvedThumbs.current.set(shapeId, thumbSrc);
        setSelectedImage((current) =>
          current?.id === shapeId ? { ...current, thumbSrc } : current,
        );
      });
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
    selectedImage,
  };
}
