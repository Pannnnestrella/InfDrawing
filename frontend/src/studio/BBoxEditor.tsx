"use client";

import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";

import type { BBox } from "@/lib/controlled-edit-api";

import { applyBBoxDrag, roundBBox, type BBoxHandle } from "./bbox-edit";

interface BBoxEditorProps {
  initial: BBox;
  label: string;
  saving: boolean;
  onSave: (bbox: BBox) => void;
  onCancel: () => void;
}

const CORNERS: { handle: Exclude<BBoxHandle, "move">; className: string }[] = [
  { handle: "nw", className: "-left-1.5 -top-1.5 cursor-nwse-resize" },
  { handle: "ne", className: "-right-1.5 -top-1.5 cursor-nesw-resize" },
  { handle: "sw", className: "-bottom-1.5 -left-1.5 cursor-nesw-resize" },
  { handle: "se", className: "-bottom-1.5 -right-1.5 cursor-nwse-resize" },
];

/** Draggable box overlay; must be rendered inside the element that frames the image. */
export function BBoxEditor({ initial, label, saving, onSave, onCancel }: BBoxEditorProps) {
  const layerRef = useRef<HTMLDivElement>(null);
  const [draft, setDraft] = useState<BBox>(initial);
  const drag = useRef<{
    handle: BBoxHandle;
    startX: number;
    startY: number;
    start: BBox;
  } | null>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, textarea, [contenteditable='true']")) return;
      if (event.key === "Escape") onCancel();
      if (event.key === "Enter" && !saving) onSave(roundBBox(draft));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [draft, saving, onSave, onCancel]);

  const begin = (handle: BBoxHandle, event: ReactPointerEvent) => {
    event.stopPropagation();
    event.preventDefault();
    layerRef.current?.setPointerCapture(event.pointerId);
    drag.current = { handle, startX: event.clientX, startY: event.clientY, start: draft };
  };

  const move = (event: ReactPointerEvent) => {
    const active = drag.current;
    const rect = layerRef.current?.getBoundingClientRect();
    if (!active || !rect || rect.width === 0 || rect.height === 0) return;
    const dx = (event.clientX - active.startX) / rect.width;
    const dy = (event.clientY - active.startY) / rect.height;
    setDraft(applyBBoxDrag(active.start, active.handle, dx, dy));
  };

  const end = (event: ReactPointerEvent) => {
    drag.current = null;
    if (layerRef.current?.hasPointerCapture(event.pointerId)) {
      layerRef.current.releasePointerCapture(event.pointerId);
    }
  };

  return (
    <div
      ref={layerRef}
      className="absolute inset-0 bg-black/30"
      onPointerMove={move}
      onPointerUp={end}
      onPointerCancel={end}
    >
      <div
        role="application"
        aria-label={`调整「${label}」的框`}
        className="absolute cursor-move border-2 border-warning bg-warning/10"
        style={{
          left: `${draft.x * 100}%`,
          top: `${draft.y * 100}%`,
          width: `${draft.w * 100}%`,
          height: `${draft.h * 100}%`,
        }}
        onPointerDown={(event) => begin("move", event)}
      >
        <span className="absolute -top-5 left-0 whitespace-nowrap rounded bg-warning px-1 text-[10px] text-black">
          {label}
        </span>
        {CORNERS.map(({ handle, className }) => (
          <span
            key={handle}
            className={`absolute h-3 w-3 rounded-sm border border-black/40 bg-warning ${className}`}
            onPointerDown={(event) => begin(handle, event)}
          />
        ))}
      </div>
      <div className="absolute bottom-3 left-1/2 flex -translate-x-1/2 items-center gap-2 rounded-lg bg-surface-0/90 px-3 py-1.5 text-xs shadow">
        <span className="text-muted">拖动移动，拖四角缩放（Enter 保存 / Esc 取消）</span>
        <button
          type="button"
          onClick={onCancel}
          className="rounded px-2 py-0.5 text-muted hover:bg-surface-2 hover:text-ink"
        >
          取消
        </button>
        <button
          type="button"
          disabled={saving}
          onClick={() => onSave(roundBBox(draft))}
          className="rounded bg-accent px-2 py-0.5 text-white hover:bg-accent-hover disabled:opacity-50"
        >
          {saving ? "保存中…" : "保存"}
        </button>
      </div>
    </div>
  );
}
