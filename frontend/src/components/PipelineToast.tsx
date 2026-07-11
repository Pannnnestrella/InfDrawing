"use client";

import { AlertIcon, CheckIcon } from "@/components/icons";
import { Spinner } from "@/components/Spinner";

export type ToastVariant = "pending" | "success" | "error";

interface PipelineToastProps {
  variant: ToastVariant;
  text: string;
}

/** Bottom-center status toast for canvas pipelines (txt2img / decompose). */
export function PipelineToast({ variant, text }: PipelineToastProps) {
  return (
    <div className="pointer-events-none fixed bottom-6 left-1/2 z-[10010] -translate-x-1/2">
      <div className="flex items-center gap-2.5 rounded-full border border-line bg-surface-1/95 py-2 pl-3 pr-4 text-xs text-ink shadow-xl backdrop-blur-md">
        {variant === "pending" ? <Spinner /> : null}
        {variant === "success" ? <CheckIcon size={14} className="text-success" /> : null}
        {variant === "error" ? <AlertIcon size={14} className="text-danger" /> : null}
        <span className={variant === "error" ? "text-danger" : undefined}>{text}</span>
      </div>
    </div>
  );
}
