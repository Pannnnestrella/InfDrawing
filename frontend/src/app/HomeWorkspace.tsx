"use client";

import { ChatPanel } from "@/agent-panel/ChatPanel";
import { InfDrawingCanvas } from "@/canvas/InfDrawingCanvas";
import { FloatingPanel } from "@/components/FloatingPanel";

export function HomeWorkspace() {
  return (
    <div className="relative h-screen w-screen overflow-hidden bg-surface-0">
      <main className="absolute inset-0">
        <InfDrawingCanvas />
      </main>
      <FloatingPanel>
        <ChatPanel />
      </FloatingPanel>
    </div>
  );
}
