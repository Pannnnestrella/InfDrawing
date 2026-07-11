"use client";

import { ChevronRightIcon, SparklesIcon } from "@/components/icons";
import { usePersistentFlag } from "@/lib/use-persistent-flag";

const STORAGE_KEY = "infdrawing-sidebar-open";

interface FloatingPanelProps {
  children: React.ReactNode;
}

/** Floating AI panel docked to the right edge of the canvas. */
export function FloatingPanel({ children }: FloatingPanelProps) {
  const [open, setOpen] = usePersistentFlag(STORAGE_KEY, true);

  if (!open) {
    return (
      <button
        type="button"
        aria-label="展开 AI 面板"
        title="展开 AI 面板"
        className="fixed right-4 top-4 z-40 flex h-11 w-11 items-center justify-center rounded-full border border-line bg-surface-1/90 text-accent shadow-xl backdrop-blur-md transition-colors hover:bg-surface-2 hover:text-accent-hover"
        onClick={() => setOpen(true)}
      >
        <SparklesIcon size={20} />
      </button>
    );
  }

  return (
    <div className="fixed bottom-3 right-3 top-3 z-40 w-[368px]">
      <button
        type="button"
        aria-label="收起 AI 面板"
        title="收起 AI 面板"
        className="absolute -left-3.5 top-1/2 z-10 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-full border border-line bg-surface-2 text-muted shadow-lg transition-colors hover:bg-surface-3 hover:text-ink"
        onClick={() => setOpen(false)}
      >
        <ChevronRightIcon size={14} />
      </button>

      <aside className="flex h-full w-full flex-col overflow-hidden rounded-2xl border border-line bg-surface-1/95 shadow-2xl backdrop-blur-md">
        {children}
      </aside>
    </div>
  );
}
