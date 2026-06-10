"use client";

import { ChatPanel } from "@/agent-panel/ChatPanel";
import { CapabilityBanner } from "@/components/CapabilityBanner";
import { SidebarShell } from "@/components/SidebarShell";
import { InfDrawingCanvas } from "@/canvas/InfDrawingCanvas";

export function HomeWorkspace() {
  return (
    <div className="relative flex h-screen w-screen overflow-hidden">
      <main className="relative min-h-0 min-w-0 flex-1">
        <InfDrawingCanvas />
      </main>
      <SidebarShell>
        <CapabilityBanner />
        <div className="min-h-0 flex-1 overflow-hidden">
          <ChatPanel />
        </div>
      </SidebarShell>
    </div>
  );
}
