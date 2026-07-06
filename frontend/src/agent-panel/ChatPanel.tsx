"use client";

import { useMemo, useState } from "react";

import { ChatComposer } from "@/agent-panel/ChatComposer";
import { useCanvasSync } from "@/agent-panel/hooks/useCanvasSync";
import { useCapabilities } from "@/agent-panel/hooks/useCapabilities";
import { useChatMessages } from "@/agent-panel/hooks/useChatMessages";
import { useChatSubmit } from "@/agent-panel/hooks/useChatSubmit";
import { useDecomposeFlow } from "@/agent-panel/hooks/useDecomposeFlow";
import type { FlowCallbacks } from "@/agent-panel/hooks/flow-types";
import { useInpaintFlow } from "@/agent-panel/hooks/useInpaintFlow";
import { useMaskEditor } from "@/agent-panel/hooks/useMaskEditor";
import { useTextEditFlow } from "@/agent-panel/hooks/useTextEditFlow";
import { useTextEditOcr } from "@/agent-panel/hooks/useTextEditOcr";
import { useTxt2ImgFlow } from "@/agent-panel/hooks/useTxt2ImgFlow";
import { MessageList } from "@/agent-panel/MessageList";
import type { ChatMode } from "@/agent-panel/types";
import { MaskTool } from "@/canvas/MaskTool";
import { theme } from "@/lib/theme";

export function ChatPanel() {
  const [message, setMessage] = useState("");
  const [mode, setMode] = useState<ChatMode>("txt2img");
  const [busy, setBusy] = useState(false);

  const { messages, appendMessage, appendStatus, appendError, notifyReconnect } =
    useChatMessages();

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

  const txt2imgFlow = useTxt2ImgFlow(flowCallbacks);
  const inpaintFlow = useInpaintFlow(flowCallbacks);
  const decomposeFlow = useDecomposeFlow(flowCallbacks);
  const textEditFlow = useTextEditFlow(flowCallbacks);

  const {
    canvasReady,
    canvasHasSelection,
    canvasHasMask,
    selectionHint,
    selectedShapeId,
  } = useCanvasSync();

  const { capabilities, modeEnabled, modeDisabledReason } = useCapabilities(mode);

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
    selectedTextIndex,
    textRegions,
    inpaintFiles: { imageFile, maskFile },
    flows: {
      txt2img: txt2imgFlow,
      inpaint: inpaintFlow,
      decompose: decomposeFlow,
      text_edit: textEditFlow,
    },
    callbacks: { appendMessage, appendStatus, appendError },
  });

  return (
    <>
      {maskEditorOpen && maskPreviewUrl ? (
        <MaskTool
          imageUrl={maskPreviewUrl}
          onComplete={(mask) => void handleMaskComplete(mask)}
          onCancel={closeMaskEditor}
        />
      ) : null}

      <div className="flex h-full flex-col" style={{ color: theme.textPrimary }}>
        <header className="shrink-0 border-b px-4 py-3" style={{ borderColor: theme.border }}>
          <h1 className="text-base font-semibold">InfDrawing</h1>
          <p className="text-xs" style={{ color: theme.textMuted }}>
            画布
            {canvasReady ? "已连接" : "加载中…"}
            {canvasHasSelection ? " · 已选图" : ""}
            {canvasHasMask ? " · Mask 就绪" : ""}
          </p>
        </header>

        <MessageList messages={messages} />

        <ChatComposer
          message={message}
          mode={mode}
          capabilities={capabilities}
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
          onSubmit={() => void handleSubmit()}
          onOpenMaskEditor={() => void openMaskEditor()}
          onSelectTextRegion={setSelectedTextIndex}
          onRetryOcr={retryOcr}
        />
      </div>
    </>
  );
}
