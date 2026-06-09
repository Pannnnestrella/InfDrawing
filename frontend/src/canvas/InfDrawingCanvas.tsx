"use client";

import { useEffect, useState } from "react";

import type { Tldraw as TldrawComponent } from "@tldraw/tldraw";

export function InfDrawingCanvas() {
  const [Tldraw, setTldraw] = useState<typeof TldrawComponent | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

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

  if (loadError) {
    return (
      <div
        className="flex h-full items-center justify-center px-6 text-center text-sm text-red-400"
        style={{ background: "var(--canvas-bg)" }}
      >
        画布加载失败：{loadError}
      </div>
    );
  }

  if (!Tldraw) {
    return (
      <div
        className="flex h-full items-center justify-center text-sm"
        style={{ color: "var(--foreground)", background: "var(--canvas-bg)" }}
      >
        画布加载中…（首次约 10–30 秒）
      </div>
    );
  }

  return (
    <div className="absolute inset-0" style={{ background: "var(--canvas-bg)" }}>
      <Tldraw persistenceKey="infdrawing-canvas-v1" />
    </div>
  );
}
