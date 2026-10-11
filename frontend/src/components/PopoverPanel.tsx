"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";

interface PopoverPanelProps {
  open: boolean;
  onClose: () => void;
  /** Anchor element used to place the panel below-right aligned. */
  anchorRef: React.RefObject<HTMLElement | null>;
  children: React.ReactNode;
  className?: string;
  /** Above FloatingPanel (500) and DraggableWindow (600). */
  zClassName?: string;
  width?: number;
}

/**
 * Fixed popover that escapes overflow:hidden ancestors (e.g. the AI side panel).
 */
export function PopoverPanel({
  open,
  onClose,
  anchorRef,
  children,
  className = "",
  zClassName = "z-[700]",
  width = 288,
}: PopoverPanelProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState({ top: 0, left: 0 });

  useLayoutEffect(() => {
    if (!open) return;
    const anchor = anchorRef.current;
    if (!anchor) return;

    const place = () => {
      const rect = anchor.getBoundingClientRect();
      const panelWidth = panelRef.current?.offsetWidth || width;
      const margin = 12;
      let left = rect.right - panelWidth;
      left = Math.max(margin, Math.min(left, window.innerWidth - panelWidth - margin));
      const top = Math.min(rect.bottom + 8, window.innerHeight - margin - 40);
      setBox({ top, left });
    };

    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open, anchorRef, width]);

  useEffect(() => {
    if (!open) return;

    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }

    function onPointerDown(event: MouseEvent) {
      const target = event.target as Node;
      if (panelRef.current?.contains(target)) return;
      if (anchorRef.current?.contains(target)) return;
      onClose();
    }

    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onPointerDown);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onPointerDown);
    };
  }, [open, onClose, anchorRef]);

  if (!open) return null;

  return (
    <div
      ref={panelRef}
      className={`fixed ${zClassName} ${className}`}
      style={{ top: box.top, left: box.left, width }}
    >
      {children}
    </div>
  );
}
