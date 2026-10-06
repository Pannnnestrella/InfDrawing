"use client";

import { useEffect, useRef, useState } from "react";

import { CloseIcon } from "@/components/icons";

/** Above the AI side panel (500); below tldraw's blocking overlay (10000). */
const WINDOW_Z = "z-[600]";
const MIN_W = 640;
const MIN_H = 480;

interface DraggableWindowProps {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
  initialWidth?: number;
  initialHeight?: number;
}

interface DragState {
  kind: "move" | "resize";
  originX: number;
  originY: number;
  startX: number;
  startY: number;
  startW: number;
  startH: number;
}

/**
 * Floating workspace window: drag the title bar, resize from the corner.
 */
export function DraggableWindow({
  title,
  children,
  onClose,
  initialWidth = 980,
  initialHeight = 700,
}: DraggableWindowProps) {
  const [box, setBox] = useState(() => ({
    x: 56,
    y: 40,
    w: initialWidth,
    h: initialHeight,
  }));
  const dragRef = useRef<DragState | null>(null);
  const stopDragRef = useRef<(() => void) | null>(null);

  useEffect(
    () => () => {
      stopDragRef.current?.();
    },
    [],
  );

  function beginDrag(kind: "move" | "resize", event: React.PointerEvent) {
    event.preventDefault();
    dragRef.current = {
      kind,
      originX: event.clientX,
      originY: event.clientY,
      startX: box.x,
      startY: box.y,
      startW: box.w,
      startH: box.h,
    };

    const onMove = (pointer: PointerEvent) => {
      const drag = dragRef.current;
      if (!drag) return;
      if (drag.kind === "move") {
        setBox((prev) => ({
          ...prev,
          x: drag.startX + pointer.clientX - drag.originX,
          y: drag.startY + pointer.clientY - drag.originY,
        }));
        return;
      }
      setBox((prev) => ({
        ...prev,
        w: Math.max(MIN_W, drag.startW + pointer.clientX - drag.originX),
        h: Math.max(MIN_H, drag.startH + pointer.clientY - drag.originY),
      }));
    };
    const onUp = () => {
      dragRef.current = null;
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      stopDragRef.current = null;
    };
    stopDragRef.current?.();
    stopDragRef.current = onUp;
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }

  return (
    <div
      role="dialog"
      aria-label={title}
      className={`fixed ${WINDOW_Z} flex flex-col overflow-hidden rounded-2xl border border-line bg-surface-1 shadow-2xl`}
      style={{ left: box.x, top: box.y, width: box.w, height: box.h }}
    >
      <header
        className="flex shrink-0 cursor-grab items-center justify-between gap-2 border-b border-line bg-surface-2/80 px-3 py-2 active:cursor-grabbing"
        onPointerDown={(event) => {
          if ((event.target as HTMLElement).closest("button")) return;
          beginDrag("move", event);
        }}
      >
        <h2 className="select-none text-sm font-semibold tracking-wide">{title}</h2>
        <button
          type="button"
          aria-label="关闭"
          title="关闭"
          className="rounded-md p-1 text-muted hover:bg-surface-3 hover:text-ink"
          onClick={onClose}
        >
          <CloseIcon size={16} />
        </button>
      </header>
      <div className="min-h-0 flex-1 overflow-hidden">{children}</div>
      <button
        type="button"
        aria-label="调整窗口大小"
        className="absolute bottom-0 right-0 h-4 w-4 cursor-nwse-resize"
        onPointerDown={(event) => beginDrag("resize", event)}
      >
        <span className="pointer-events-none absolute bottom-1 right-1 h-2 w-2 border-b-2 border-r-2 border-muted" />
      </button>
    </div>
  );
}
