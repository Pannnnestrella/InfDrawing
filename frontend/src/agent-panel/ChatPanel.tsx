"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { ChatComposer } from "@/agent-panel/ChatComposer";
import { useCanvasSync } from "@/agent-panel/hooks/useCanvasSync";
import { useCapabilities } from "@/agent-panel/hooks/useCapabilities";
import { useChatMessages } from "@/agent-panel/hooks/useChatMessages";
import { useChatSubmit } from "@/agent-panel/hooks/useChatSubmit";
import { useDecomposeFlow } from "@/agent-panel/hooks/useDecomposeFlow";
import type { FlowCallbacks } from "@/agent-panel/hooks/flow-types";
import { useImageEditFlow } from "@/agent-panel/hooks/useImageEditFlow";
import { useInpaintFlow } from "@/agent-panel/hooks/useInpaintFlow";
import { useMaskEditor } from "@/agent-panel/hooks/useMaskEditor";
import { useTextEditFlow } from "@/agent-panel/hooks/useTextEditFlow";
import { useTextEditOcr } from "@/agent-panel/hooks/useTextEditOcr";
import { useTxt2ImgFlow } from "@/agent-panel/hooks/useTxt2ImgFlow";
import { MessageList } from "@/agent-panel/MessageList";
import { SessionSwitcher } from "@/agent-panel/SessionSwitcher";
import type { ChatMode } from "@/agent-panel/types";
import { MaskTool } from "@/canvas/MaskTool";
import { ApiKeyControl } from "@/components/ApiKeyControl";
import { CapabilityStatus } from "@/components/CapabilityStatus";
import {
  loadEnginePreference,
  resolveImageBackend,
  saveEnginePreference,
  type EnginePreference,
} from "@/lib/engine-preference";

export function ChatPanel({
  onOpenStudio,
  onOpenLibrary,
}: {
  onOpenStudio?: () => void;
  onOpenLibrary?: () => void;
}) {
  const [message, setMessage] = useState("");
  const [mode, setMode] = useState<ChatMode>("auto");
  const [busy, setBusy] = useState(false);
  const [enginePreference, setEnginePreference] = useState<EnginePreference>({
    mode: "auto",
    cloudProvider: "openai",
  });

  useEffect(() => {
    setEnginePreference(loadEnginePreference());
  }, []);

  const {
    sessions,
    activeSessionId,
    messages,
    beginSession,
    selectSession,
    startNewChat,
    clearAllSessions,
    appendMessage,
    appendStatus,
    appendError,
    notifyReconnect,
  } = useChatMessages();

  const flowCallbacks: FlowCallbacks = useMemo(
    () => ({
      appendMessage,
      appendStatus,
      appendError,
      notifyReconnect,
      setBusy,
    }),
    [appendMessage, appendStatus, appendError, notifyReconnect],
  );

  const { capabilities, modeEnabled, modeDisabledReason } = useCapabilities(mode);

  const getBackend = useCallback(
    () => resolveImageBackend(enginePreference, capabilities),
    [enginePreference, capabilities],
  );

  const txt2imgFlow = useTxt2ImgFlow(flowCallbacks, getBackend);
  const inpaintFlow = useInpaintFlow(flowCallbacks, getBackend);
  const imageEditFlow = useImageEditFlow(flowCallbacks);
  const decomposeFlow = useDecomposeFlow(flowCallbacks);
  const textEditFlow = useTextEditFlow(flowCallbacks);

  const {
    canvasReady,
    canvasHasSelection,
    canvasHasMask,
    selectionHint,
    selectedShapeId,
  } = useCanvasSync();

  const {
    imageFile,
    maskFile,
    maskEditorOpen,
    maskPreviewUrl,
    openMaskEditor,
    closeMaskEditor,
    handleMaskComplete,
  } = useMaskEditor({ appendStatus, appendError });

  const {
    textRegions,
    selectedTextIndex,
    setSelectedTextIndex,
    ocrLoading,
    ocrError,
    retryOcr,
  } = useTextEditOcr(mode, selectedShapeId);

  const { handleSubmit } = useChatSubmit({
    mode,
    message,
    setMessage,
    busy,
    setBusy,
    modeEnabled,
    modeDisabledReason,
    capabilities,
    selectedTextIndex,
    textRegions,
    ocrLoading,
    ocrError,
    inpaintFiles: { imageFile, maskFile },
    flows: {
      txt2img: txt2imgFlow,
      inpaint: inpaintFlow,
      image_edit: imageEditFlow,
      decompose: decomposeFlow,
      text_edit: textEditFlow,
    },
    beginSession,
    callbacks: { appendMessage, appendStatus, appendError },
  });

  function handleEngineChange(next: EnginePreference) {
    setEnginePreference(next);
    saveEnginePreference(next);
  }

  return (
    <>
      {maskEditorOpen && maskPreviewUrl ? (
        <MaskTool
          imageUrl={maskPreviewUrl}
          onComplete={(mask) => void handleMaskComplete(mask)}
          onCancel={closeMaskEditor}
        />
      ) : null}

      <div className="flex h-full flex-col text-ink">
        <header className="flex shrink-0 items-start justify-between gap-2 border-b border-line px-4 py-3">
          <div>
            <h1 className="text-sm font-semibold tracking-wide">InfDrawing</h1>
            <p className="mt-0.5 text-[11px] text-muted">
              画布{canvasReady ? "已连接" : "加载中…"}
              {canvasHasSelection ? " · 已选图" : ""}
              {canvasHasMask ? " · Mask 就绪" : ""}
            </p>
          </div>
          <div className="flex items-center gap-1.5">
            <ApiKeyControl />
            <CapabilityStatus />
          </div>
        </header>

        <SessionSwitcher
          sessions={sessions}
          activeSessionId={activeSessionId}
          busy={busy}
          onSelect={selectSession}
          onNewChat={startNewChat}
          onClearAll={clearAllSessions}
        />

        <MessageList messages={messages} busy={busy} />

        <ChatComposer
          message={message}
          mode={mode}
          capabilities={capabilities}
          enginePreference={enginePreference}
          busy={busy}
          modeEnabled={modeEnabled}
          modeDisabledReason={modeDisabledReason}
          selectionHint={selectionHint}
          canvasReady={canvasReady}
          canvasHasSelection={canvasHasSelection}
          canvasHasMask={canvasHasMask}
          textRegions={textRegions}
          selectedTextIndex={selectedTextIndex}
          ocrLoading={ocrLoading}
          ocrError={ocrError}
          onMessageChange={setMessage}
          onModeChange={setMode}
          onEngineChange={handleEngineChange}
          onSubmit={() => void handleSubmit()}
          onOpenMaskEditor={() => void openMaskEditor()}
          onSelectTextRegion={setSelectedTextIndex}
          onRetryOcr={retryOcr}
          onOpenStudio={onOpenStudio}
          onOpenLibrary={onOpenLibrary}
        />
      </div>
    </>
  );
}
