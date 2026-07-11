"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { INPAINT_CANVAS_SIZE } from "@/canvas/types";
import { BrushIcon } from "@/components/icons";

interface MaskToolProps {
  imageUrl: string;
  onComplete: (maskFile: File) => void;
  onCancel: () => void;
}

const DEFAULT_BRUSH_RADIUS = 14;

export function MaskTool({ imageUrl, onComplete, onCancel }: MaskToolProps) {
  const displayRef = useRef<HTMLCanvasElement>(null);
  const maskRef = useRef<HTMLCanvasElement>(null);
  const drawingRef = useRef(false);

  const [ready, setReady] = useState(false);
  const [brushSize, setBrushSize] = useState(DEFAULT_BRUSH_RADIUS);

  useEffect(() => {
    let cancelled = false;
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      if (cancelled) return;
      const display = displayRef.current;
      const mask = maskRef.current;
      if (!display || !mask) return;

      const size = INPAINT_CANVAS_SIZE;
      display.width = size;
      display.height = size;
      mask.width = size;
      mask.height = size;

      const dctx = display.getContext("2d");
      const mctx = mask.getContext("2d");
      if (!dctx || !mctx) return;

      dctx.drawImage(img, 0, 0, size, size);
      mctx.fillStyle = "#000000";
      mctx.fillRect(0, 0, size, size);
      setReady(true);
    };
    img.onerror = () => {
      if (!cancelled) setReady(false);
    };
    img.src = imageUrl;

    return () => {
      cancelled = true;
    };
  }, [imageUrl]);

  const paint = useCallback(
    (clientX: number, clientY: number) => {
      const display = displayRef.current;
      const mask = maskRef.current;
      if (!display || !mask) return;
      const rect = display.getBoundingClientRect();
      const x = ((clientX - rect.left) / rect.width) * display.width;
      const y = ((clientY - rect.top) / rect.height) * display.height;

      const dctx = display.getContext("2d");
      const mctx = mask.getContext("2d");
      if (!dctx || !mctx) return;

      dctx.globalAlpha = 0.45;
      dctx.fillStyle = "#ffffff";
      dctx.beginPath();
      dctx.arc(x, y, brushSize, 0, Math.PI * 2);
      dctx.fill();
      dctx.globalAlpha = 1;

      mctx.fillStyle = "#ffffff";
      mctx.beginPath();
      mctx.arc(x, y, brushSize, 0, Math.PI * 2);
      mctx.fill();
    },
    [brushSize],
  );

  const handlePointerDown = (event: React.PointerEvent<HTMLCanvasElement>) => {
    drawingRef.current = true;
    event.currentTarget.setPointerCapture(event.pointerId);
    paint(event.clientX, event.clientY);
  };

  const handlePointerMove = (event: React.PointerEvent<HTMLCanvasElement>) => {
    if (!drawingRef.current) return;
    paint(event.clientX, event.clientY);
  };

  const handlePointerUp = (event: React.PointerEvent<HTMLCanvasElement>) => {
    drawingRef.current = false;
    event.currentTarget.releasePointerCapture(event.pointerId);
  };

  const handleClear = () => {
    const display = displayRef.current;
    const mask = maskRef.current;
    if (!display || !mask) return;
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      const dctx = display.getContext("2d");
      const mctx = mask.getContext("2d");
      if (!dctx || !mctx) return;
      dctx.drawImage(img, 0, 0, display.width, display.height);
      mctx.fillStyle = "#000000";
      mctx.fillRect(0, 0, mask.width, mask.height);
    };
    img.src = imageUrl;
  };

  const handleExport = async () => {
    const mask = maskRef.current;
    if (!mask) return;
    const blob = await new Promise<Blob>((resolve, reject) => {
      mask.toBlob(
        (b) => (b ? resolve(b) : reject(new Error("mask export failed"))),
        "image/png",
      );
    });
    onComplete(new File([blob], "canvas_mask.png", { type: "image/png" }));
  };

  return (
    <div
      className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/60 p-4 backdrop-blur-[2px]"
      role="dialog"
      aria-modal="true"
      aria-label="Mask 刷选"
    >
      <div className="flex max-h-[90vh] w-full max-w-lg flex-col rounded-2xl border border-line bg-surface-1 p-4 shadow-2xl">
        <div className="mb-2 flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-surface-2 text-accent">
            <BrushIcon size={16} />
          </span>
          <h2 className="text-sm font-semibold text-ink">刷选重绘区域</h2>
        </div>
        <p className="mb-3 text-[11px] text-muted">
          在图片上刷涂需要重绘的区域（{INPAINT_CANVAS_SIZE}×{INPAINT_CANVAS_SIZE}）。
          未涂=保留，涂白=重绘。
        </p>

        <div className="relative mx-auto mb-3 aspect-square w-full max-w-[512px] overflow-hidden rounded-xl border border-line">
          <canvas
            ref={displayRef}
            className="h-full w-full cursor-crosshair touch-none"
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onPointerLeave={handlePointerUp}
          />
          <canvas ref={maskRef} className="hidden" aria-hidden />
        </div>

        <label className="mb-3 flex items-center gap-2 text-[11px] text-muted">
          笔刷大小
          <input
            type="range"
            min={4}
            max={48}
            value={brushSize}
            onChange={(e) => setBrushSize(Number(e.target.value))}
            className="flex-1 accent-accent"
          />
          <span className="w-9 text-right tabular-nums">{brushSize}px</span>
        </label>

        <div className="flex justify-end gap-2">
          <button
            type="button"
            className="rounded-lg px-3 py-1.5 text-sm text-muted transition-colors hover:bg-surface-2 hover:text-ink"
            onClick={onCancel}
          >
            取消
          </button>
          <button
            type="button"
            className="rounded-lg border border-line bg-surface-2 px-3 py-1.5 text-sm text-ink transition-colors hover:bg-surface-3 disabled:opacity-40"
            onClick={handleClear}
            disabled={!ready}
          >
            清除
          </button>
          <button
            type="button"
            className="rounded-lg bg-accent px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-accent-hover disabled:opacity-40"
            onClick={() => void handleExport()}
            disabled={!ready}
          >
            确认 Mask
          </button>
        </div>
      </div>
    </div>
  );
}
