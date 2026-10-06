"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  Tldraw,
  type Editor,
  type TLComponents,
} from "@tldraw/tldraw";
import "@tldraw/tldraw/tldraw.css";

import { AiContextMenu } from "@/canvas/AiContextMenu";
import { AiGenerateOverlay } from "@/canvas/AiGenerateOverlay";
import { DecomposeOverlay } from "@/canvas/DecomposeOverlay";
import { LibraryIngestDialog } from "@/library/LibraryIngestDialog";
import { Spinner } from "@/components/Spinner";
import {
  registerCanvasEditor,
  unregisterCanvasEditor,
} from "@/lib/canvas-bridge";

export function InfDrawingCanvas() {
  // Mount tldraw only after client hydration to avoid SSR/client tree mismatch.
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);

  const components = useMemo<TLComponents>(
    () => ({
      ContextMenu: AiContextMenu,
    }),
    [],
  );

  const handleMount = useCallback((editor: Editor) => {
    registerCanvasEditor(editor);
    return () => unregisterCanvasEditor();
  }, []);

  if (!mounted) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 bg-[var(--canvas-bg)]">
        <Spinner size={22} />
        <p className="text-sm text-muted">画布加载中…（首次约 10–30 秒）</p>
      </div>
    );
  }

  return (
    <div className="absolute inset-0 bg-[var(--canvas-bg)]">
      <Tldraw
        persistenceKey="infdrawing-canvas-v1"
        colorScheme="light"
        onMount={handleMount}
        components={components}
      />
      <AiGenerateOverlay />
      <DecomposeOverlay />
      <LibraryIngestDialog />
    </div>
  );
}
