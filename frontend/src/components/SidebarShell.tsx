"use client";

import { useEffect, useState } from "react";

import { theme } from "@/lib/theme";

const STORAGE_KEY = "infdrawing-sidebar-open";

interface SidebarShellProps {
  children: React.ReactNode;
}

export function SidebarShell({ children }: SidebarShellProps) {
  const [open, setOpen] = useState(true);

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "0") setOpen(false);
  }, []);

  function toggle(next: boolean) {
    setOpen(next);
    window.localStorage.setItem(STORAGE_KEY, next ? "1" : "0");
  }

  return (
    <>
      <button
        type="button"
        aria-label={open ? "收起侧边栏" : "展开侧边栏"}
        title={open ? "收起侧边栏" : "展开侧边栏"}
        className="absolute top-1/2 z-20 -translate-y-1/2 rounded-l-md border border-r-0 px-1 py-3 text-xs shadow-md transition-[right] duration-200"
        style={{
          right: open ? 360 : 0,
          background: theme.surface,
          borderColor: theme.border,
          color: theme.textMuted,
        }}
        onClick={() => toggle(!open)}
      >
        {open ? "›" : "‹"}
      </button>

      <aside
        className="flex shrink-0 flex-col border-l transition-[width] duration-200 ease-out"
        style={{
          width: open ? 360 : 0,
          borderColor: open ? "var(--border)" : "transparent",
          background: "var(--bg-panel)",
          overflow: "hidden",
        }}
      >
        <div className="flex h-full w-[360px] flex-col">{children}</div>
      </aside>
    </>
  );
}
