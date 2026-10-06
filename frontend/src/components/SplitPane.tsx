"use client";

import { useEffect, useRef, type ReactNode } from "react";

type Axis = "x" | "y";

interface SplitPaneProps {
  axis: Axis;
  /** Pixel size of the trailing pane (right for x, bottom for y). */
  secondarySize: number;
  minSecondary: number;
  minPrimary: number;
  onSecondarySizeChange: (size: number) => void;
  label: string;
  children: [ReactNode, ReactNode];
}

/**
 * Two-pane flex split. Drag the separator to resize the trailing pane.
 */
export function SplitPane({
  axis,
  secondarySize,
  minSecondary,
  minPrimary,
  onSecondarySizeChange,
  label,
  children,
}: SplitPaneProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ start: number; startSize: number } | null>(null);
  const stopDragRef = useRef<(() => void) | null>(null);
  const horizontal = axis === "x";
  const [primary, secondary] = children;

  useEffect(
    () => () => {
      stopDragRef.current?.();
    },
    [],
  );

  function beginDrag(event: React.PointerEvent<HTMLButtonElement>) {
    event.preventDefault();
    dragRef.current = {
      start: horizontal ? event.clientX : event.clientY,
      startSize: secondarySize,
    };
    const onMove = (pointer: PointerEvent) => {
      const drag = dragRef.current;
      if (!drag) return;
      const current = horizontal ? pointer.clientX : pointer.clientY;
      const rect = containerRef.current?.getBoundingClientRect();
      const total = horizontal ? (rect?.width ?? 0) : (rect?.height ?? 0);
      const maxSecondary = Math.max(minSecondary, total - minPrimary);
      const next = drag.startSize - (current - drag.start);
      onSecondarySizeChange(Math.min(maxSecondary, Math.max(minSecondary, next)));
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
      ref={containerRef}
      className={`flex h-full min-h-0 min-w-0 w-full ${horizontal ? "flex-row" : "flex-col"}`}
    >
      <div className="min-h-0 min-w-0 flex-1 overflow-hidden">{primary}</div>
      <button
        type="button"
        aria-label={label}
        aria-orientation={horizontal ? "vertical" : "horizontal"}
        className={`shrink-0 border-line bg-surface-2/80 hover:bg-accent/40 ${
          horizontal
            ? "w-1.5 cursor-col-resize border-x"
            : "h-1.5 cursor-row-resize border-y"
        }`}
        onPointerDown={beginDrag}
      />
      <div
        className="min-h-0 min-w-0 shrink-0 overflow-hidden"
        style={horizontal ? { width: secondarySize } : { height: secondarySize }}
      >
        {secondary}
      </div>
    </div>
  );
}
