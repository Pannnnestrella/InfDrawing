"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import type { Editor, Tldraw as TldrawComponent, TLComponents } from "@tldraw/tldraw";

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
  const [Tldraw, setTldraw] = useState<typeof TldrawComponent | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const components = useMemo<TLComponents>(
    () => ({
      ContextMenu: AiContextMenu,
    }),
    [],
  );

  useEffect(() => {
    let cancelled = false;

    async function loadCanvas() {
      try {
        await import("@tldraw/tldraw/tldraw.css");
        const mod = await import("@tldraw/tldraw");
        if (!cancelled) {
          setTldraw(() => mod.Tldraw);
        }
      } catch (error) {
        if (!cancelled) {
          setLoadError(error instanceof Error ? error.message : "tldraw 加载失败");
        }
      }
    }

    void loadCanvas();

    return () => {
      cancelled = true;
    };
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

  if (!Tldraw) {
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
        colorScheme="dark"
        onMount={handleMount}
        components={components}
      />
      <AiGenerateOverlay />
      <DecomposeOverlay />
    </div>
  );
}
