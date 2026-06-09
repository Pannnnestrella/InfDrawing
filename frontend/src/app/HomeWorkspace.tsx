"use client";

import { ChatPanel } from "@/agent-panel/ChatPanel";
import { InfDrawingCanvas } from "@/canvas/InfDrawingCanvas";

export function HomeWorkspace() {
  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <main className="relative min-h-0 min-w-0 flex-1">
        <InfDrawingCanvas />
      </main>
      <aside
        className="w-[360px] shrink-0 border-l"
        style={{ borderColor: "var(--border)", background: "var(--bg-panel)" }}
      >
        <ChatPanel />
      </aside>
    </div>
  );
}
