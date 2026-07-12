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
import { AlertIcon } from "@/components/icons";
import { Spinner } from "@/components/Spinner";
import {
  registerCanvasEditor,
  unregisterCanvasEditor,
} from "@/lib/canvas-bridge";

export function InfDrawingCanvas() {
  const [mounted, setMounted] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const components = useMemo<TLComponents>(
    () => ({
      ContextMenu: AiContextMenu,
    }),
    [],
  );

  useEffect(() => {
    try {
      setMounted(true);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "tldraw 加载失败");
    }
  }, []);

  const handleMount = useCallback((editor: Editor) => {
    registerCanvasEditor(editor);
    return () => unregisterCanvasEditor();
  }, []);

  if (loadError) {
    return (
      <div className="flex h-full items-center justify-center bg-[var(--canvas-bg)] px-6">
        <p className="flex items-center gap-2 text-center text-sm text-danger">
          <AlertIcon size={16} />
          画布加载失败：{loadError}
        </p>
      </div>
    );
  }

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
    </div>
  );
}
