"use client";

import { useEffect, useState } from "react";

import { AlertIcon, CheckIcon, CloseIcon } from "@/components/icons";
import { Spinner } from "@/components/Spinner";
import {
  dismissCanvasToast,
  getCanvasToast,
  subscribeCanvasToast,
  type CanvasToast,
} from "@/lib/canvas-toast-store";

/** Bottom-center dismissible toast host for cross-cutting canvas alerts. */
export function CanvasToastHost() {
  const [toast, setToast] = useState<CanvasToast | null>(() => getCanvasToast());

  useEffect(() => subscribeCanvasToast(() => setToast(getCanvasToast())), []);

  if (!toast) return null;

  return (
    <div className="pointer-events-none fixed bottom-6 left-1/2 z-[10010] -translate-x-1/2">
      <div
        className="pointer-events-auto flex max-w-[min(92vw,420px)] items-start gap-2.5 rounded-2xl border border-line bg-surface-1/95 py-2.5 pl-3 pr-2 text-xs text-ink shadow-xl backdrop-blur-md"
        role="alert"
      >
        {toast.variant === "pending" ? <Spinner /> : null}
        {toast.variant === "success" ? (
          <CheckIcon size={14} className="mt-0.5 shrink-0 text-success" />
        ) : null}
        {toast.variant === "error" ? (
          <AlertIcon size={14} className="mt-0.5 shrink-0 text-danger" />
        ) : null}
        <span className={`min-w-0 flex-1 leading-snug ${toast.variant === "error" ? "text-danger" : ""}`}>
          {toast.text}
        </span>
        <button
          type="button"
          aria-label="关闭提示"
          title="关闭"
          className="shrink-0 rounded-md p-1 text-muted transition-colors hover:bg-surface-3 hover:text-ink"
          onClick={() => dismissCanvasToast(toast.id)}
        >
          <CloseIcon size={14} />
        </button>
      </div>
    </div>
  );
}
