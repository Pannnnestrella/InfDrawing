"use client";

import { useEffect, useState } from "react";

import { ChatPanel } from "@/agent-panel/ChatPanel";
import { InfDrawingCanvas } from "@/canvas/InfDrawingCanvas";
import { CanvasToastHost } from "@/components/CanvasToastHost";
import { DraggableWindow } from "@/components/DraggableWindow";
import { FloatingPanel } from "@/components/FloatingPanel";
import { LayerPanel } from "@/layers/LayerPanel";
import {
  isLayerPanelOpen,
  setLayerPanelOpen,
  subscribeLayerPanel,
} from "@/layers/layer-panel-store";
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
  const [layersOpen, setLayersOpen] = useState(isLayerPanelOpen);

  useEffect(() => subscribeLibraryPanel(() => setLibraryOpen(isLibraryPanelOpen())), []);
  useEffect(() => subscribeLayerPanel(() => setLayersOpen(isLayerPanelOpen())), []);

  return (
    <div className="relative h-screen w-screen overflow-hidden bg-surface-0">
      <main className="absolute inset-0">
        <InfDrawingCanvas />
      </main>
      <FloatingPanel>
        <ChatPanel
          onOpenStudio={() => setStudioOpen(true)}
          onOpenLibrary={() => setLibraryPanelOpen(true)}
          onOpenLayers={() => setLayerPanelOpen(true)}
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
      {layersOpen ? (
        <DraggableWindow
          title="图层"
          onClose={() => setLayerPanelOpen(false)}
          initialWidth={360}
          initialHeight={520}
          minWidth={300}
          minHeight={360}
        >
          <LayerPanel />
        </DraggableWindow>
      ) : null}
      <CanvasToastHost />
    </div>
  );
}
