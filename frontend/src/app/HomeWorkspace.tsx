"use client";

import { useEffect, useState } from "react";

import { ChatPanel } from "@/agent-panel/ChatPanel";
import { InfDrawingCanvas } from "@/canvas/InfDrawingCanvas";
import { DraggableWindow } from "@/components/DraggableWindow";
import { FloatingPanel } from "@/components/FloatingPanel";
import { LibraryPanel } from "@/library/LibraryPanel";
import {
  isLibraryPanelOpen,
  setLibraryPanelOpen,
  subscribeLibraryPanel,
} from "@/library/library-panel-store";
import { StudioWorkspace } from "@/studio/StudioWorkspace";

export function HomeWorkspace() {
  const [studioOpen, setStudioOpen] = useState(false);
  const [libraryOpen, setLibraryOpen] = useState(isLibraryPanelOpen);

  useEffect(() => subscribeLibraryPanel(() => setLibraryOpen(isLibraryPanelOpen())), []);

  return (
    <div className="relative h-screen w-screen overflow-hidden bg-surface-0">
      <main className="absolute inset-0">
        <InfDrawingCanvas />
      </main>
      <FloatingPanel>
        <ChatPanel
          onOpenStudio={() => setStudioOpen(true)}
          onOpenLibrary={() => setLibraryPanelOpen(true)}
        />
      </FloatingPanel>
      {studioOpen ? (
        <DraggableWindow title="多轮编辑" onClose={() => setStudioOpen(false)}>
          <StudioWorkspace layout="float" />
        </DraggableWindow>
      ) : null}
      {libraryOpen ? (
        <DraggableWindow
          title="素材库"
          onClose={() => setLibraryPanelOpen(false)}
          initialWidth={940}
          initialHeight={640}
        >
          <LibraryPanel />
        </DraggableWindow>
      ) : null}
    </div>
  );
}
