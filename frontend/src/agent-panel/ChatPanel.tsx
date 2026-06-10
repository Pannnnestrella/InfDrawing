"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ChatComposer } from "@/agent-panel/ChatComposer";
import { MessageList } from "@/agent-panel/MessageList";
import {
  createMessageId,
  MODE_LABELS,
  type ChatMessage,
  type ChatMode,
} from "@/agent-panel/types";
import { MaskTool } from "@/canvas/MaskTool";
import {
  exportSelectedImageFile,
  exportSelectedImageForInpaint,
  getCanvasContextSnapshot,
  getCanvasEditor,
  getCanvasMaskPair,
  getCanvasSelectionHint,
  getSelectedImageAnchor,
  getSelectedImagePreviewUrl,
  overlayTextOnSelectedImage,
  pasteImageUrlToCanvas,
  pasteLayersToCanvas,
  replaceSelectedImageSrc,
  setCanvasMaskPair,
  subscribeCanvasBridge,
} from "@/lib/canvas-bridge";
import {
  featureReason,
  fetchCapabilities,
  isModeEnabled,
  type CapabilitiesResponse,
} from "@/lib/capabilities";
import {
  detectTextRegions,
  requestPlan,
  submitDecompose,
  submitInpaint,
  submitTextEdit,
  submitTxt2Img,
  type TextRegion,
} from "@/lib/api";
import { runGenerateTask } from "@/lib/generate-task";
import { theme } from "@/lib/theme";

const DECOMPOSE_DEFAULT_PROMPT = "clean seamless background, high quality";

export function ChatPanel() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [message, setMessage] = useState("");
  const [mode, setMode] = useState<ChatMode>("txt2img");
  const [busy, setBusy] = useState(false);
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [maskFile, setMaskFile] = useState<File | null>(null);
  const [canvasReady, setCanvasReady] = useState(false);
  const [canvasHasSelection, setCanvasHasSelection] = useState(false);
  const [canvasHasMask, setCanvasHasMask] = useState(false);
  const [selectionHint, setSelectionHint] = useState<string | null>("画布加载中…");
  const [maskEditorOpen, setMaskEditorOpen] = useState(false);
  const [maskPreviewUrl, setMaskPreviewUrl] = useState<string | null>(null);
  const [capabilities, setCapabilities] = useState<CapabilitiesResponse | null>(null);
  const [textRegions, setTextRegions] = useState<TextRegion[]>([]);
  const [selectedTextIndex, setSelectedTextIndex] = useState<number | null>(null);
  const [ocrLoading, setOcrLoading] = useState(false);
  const [ocrError, setOcrError] = useState<string | null>(null);
  const [selectedShapeId, setSelectedShapeId] = useState<string | null>(null);
  const lastOcrShapeRef = useRef<string | null>(null);

  const appendMessage = useCallback((entry: ChatMessage) => {
    setMessages((prev) => [...prev, entry]);
  }, []);

  const appendStatus = useCallback(
    (text: string) => {
      appendMessage({ id: createMessageId(), role: "assistant", kind: "status", text });
    },
    [appendMessage],
  );

  const appendError = useCallback(
    (text: string) => {
      appendMessage({ id: createMessageId(), role: "assistant", kind: "error", text });
    },
    [appendMessage],
  );

  useEffect(() => {
    void fetchCapabilities()
      .then(setCapabilities)
      .catch(() => setCapabilities(null));
  }, []);

  const modeEnabled = isModeEnabled(capabilities, mode);
  const modeDisabledReason = featureReason(
    capabilities,
    mode === "txt2img"
      ? "txt2img"
      : mode === "inpaint"
        ? "inpaint"
        : mode === "decompose"
          ? "decompose"
          : "text_edit",
  );

  const runOcr = useCallback(async () => {
    setOcrLoading(true);
    setOcrError(null);
    setTextRegions([]);
    setSelectedTextIndex(null);
    try {
      const file = await exportSelectedImageFile();
      if (!file) {
        setOcrError("无法导出选中图片");
        return;
      }
      const result = await detectTextRegions(file);
      setTextRegions(result.regions);
      if (result.regions.length > 0) {
        setSelectedTextIndex(0);
      }
    } catch (err) {
      setOcrError(err instanceof Error ? err.message : "OCR 检测失败");
    } finally {
      setOcrLoading(false);
    }
  }, []);

  useEffect(() => {
    const sync = () => {
      setCanvasReady(getCanvasEditor() !== null);
      const ctx = getCanvasContextSnapshot();
      setCanvasHasSelection(ctx.selectedShapeId !== null);
      setCanvasHasMask(ctx.hasMask);
      setSelectionHint(getCanvasSelectionHint());
      setSelectedShapeId(ctx.selectedShapeId);
    };
    sync();
    const unsub = subscribeCanvasBridge(sync);
    const timer = window.setInterval(sync, 400);
    return () => {
      unsub();
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (mode !== "text_edit") {
      lastOcrShapeRef.current = null;
      return;
    }
    if (!selectedShapeId) return;
    if (lastOcrShapeRef.current === selectedShapeId) return;
    lastOcrShapeRef.current = selectedShapeId;
    void runOcr();
  }, [mode, selectedShapeId, runOcr]);

  function retryOcr() {
    lastOcrShapeRef.current = null;
    void runOcr();
  }

  async function handleGenerationComplete(imageUrl: string, caption?: string) {
    appendMessage({
      id: createMessageId(),
      role: "assistant",
      kind: "image",
      imageUrl,
      caption,
    });
    try {
      const pasted = await pasteImageUrlToCanvas(imageUrl);
      if (!pasted) {
        appendError("生成成功，但画布未就绪（结果仍可在上方预览）");
      } else {
        appendStatus("已回贴到画布");
      }
    } catch (err) {
      appendError(
        err instanceof Error ? `回贴画布失败：${err.message}` : "回贴画布失败",
      );
    }
  }

  async function openMaskEditor() {
    const url = await getSelectedImagePreviewUrl();
    if (!url) {
      appendError("请先在画布上选中一张图片");
      return;
    }
    setMaskPreviewUrl(url);
    setMaskEditorOpen(true);
  }

  async function handleMaskComplete(mask: File) {
    try {
      const image = await exportSelectedImageForInpaint();
      if (!image) {
        appendError("无法导出选中图片");
        return;
      }
      setCanvasMaskPair({ image, mask });
      setImageFile(image);
      setMaskFile(mask);
      setMaskEditorOpen(false);
      setMaskPreviewUrl(null);
      appendStatus("Mask 已就绪，可以发送局部重绘指令");
    } catch (err) {
      appendError(err instanceof Error ? err.message : "Mask 导出失败");
    }
  }

  async function handleSubmit() {
    const text = message.trim();
    if (mode !== "decompose" && !text) return;
    if (mode === "text_edit" && selectedTextIndex === null) {
      appendError("请先选择要替换的文字块");
      return;
    }
    if (!modeEnabled) {
      appendError(modeDisabledReason ?? "当前环境不支持此功能");
      return;
    }
    if (busy) return;

    const userText = text || (mode === "decompose" ? DECOMPOSE_DEFAULT_PROMPT : "");
    appendMessage({
      id: createMessageId(),
      role: "user",
      mode,
      text: text || (mode === "decompose" ? "（使用默认背景风格）" : userText),
    });
    setMessage("");
    setBusy(true);

    try {
      appendStatus("理解意图中…");
      const plan = await requestPlan({
        user_message: userText,
        intent_override: mode,
        context: getCanvasContextSnapshot(),
      });
      appendStatus(`${MODE_LABELS[mode]} · ${plan.refined_prompt}`);

      if (plan.intent === "txt2img") {
        appendStatus("生图任务已提交…");
        const { task_id } = await submitTxt2Img(plan.refined_prompt, "auto");
        runGenerateTask(task_id, {
          onProgress: () => appendStatus("生图进行中…"),
          onComplete: async (url) => {
            await handleGenerationComplete(url);
            setBusy(false);
          },
          onError: (msg) => {
            appendError(msg);
            setBusy(false);
          },
        });
        return;
      }

      if (plan.intent === "inpaint") {
        const canvasPair = getCanvasMaskPair();
        const resolvedImage = canvasPair?.image ?? imageFile;
        const resolvedMask = canvasPair?.mask ?? maskFile;

        if (!resolvedImage || !resolvedMask) {
          appendError("局部重绘需要原图和 Mask：选中图片后刷选 Mask");
          setBusy(false);
          return;
        }

        appendStatus("局部重绘任务已提交…");
        const { task_id } = await submitInpaint({
          image: resolvedImage,
          mask: resolvedMask,
          prompt: plan.refined_prompt,
        });
        runGenerateTask(task_id, {
          onProgress: () => appendStatus("局部重绘进行中…"),
          onComplete: async (url) => {
            await handleGenerationComplete(url);
            setBusy(false);
          },
          onError: (msg) => {
            appendError(msg);
            setBusy(false);
          },
        });
        return;
      }

      if (plan.intent === "decompose") {
        const anchor = getSelectedImageAnchor();
        if (!anchor) {
          appendError("元素拆解需要先在画布上选中一张图片");
          setBusy(false);
          return;
        }

        const imageFileForDecompose = await exportSelectedImageFile();
        if (!imageFileForDecompose) {
          appendError("无法导出选中图片");
          setBusy(false);
          return;
        }

        appendStatus("元素拆解任务已提交…");
        const { task_id } = await submitDecompose(imageFileForDecompose, plan.refined_prompt);
        runGenerateTask(task_id, {
          onProgress: (step) => {
            const labels: Record<string, string> = {
              segmenting: "分割主体…",
              extracting: "提取前景…",
              inpainting: "补全背景…",
            };
            appendStatus(labels[step ?? ""] ?? "元素拆解进行中…");
          },
          onComplete: async (_url, layers) => {
            try {
              if (!layers?.length) {
                appendError("未收到图层数据");
                setBusy(false);
                return;
              }
              const pasted = await pasteLayersToCanvas(layers, anchor);
              if (!pasted) {
                appendError("拆解成功，但回贴画布失败");
              } else {
                appendStatus(`已回贴 ${layers.length} 个图层到画布`);
              }
            } catch (err) {
              appendError(err instanceof Error ? err.message : "回贴失败");
            }
            setBusy(false);
          },
          onError: (msg) => {
            appendError(msg);
            setBusy(false);
          },
        });
        return;
      }

      if (plan.intent === "text_edit") {
        const region =
          selectedTextIndex !== null ? textRegions[selectedTextIndex] : undefined;
        if (!region) {
          appendError("请选择要替换的文字块");
          setBusy(false);
          return;
        }

        const imageFileForEdit = await exportSelectedImageFile();
        if (!imageFileForEdit) {
          appendError("无法导出选中图片");
          setBusy(false);
          return;
        }

        appendStatus("文字编辑任务已提交…");
        const { task_id } = await submitTextEdit({
          image: imageFileForEdit,
          bbox: region.bbox,
          newText: plan.refined_prompt,
        });
        runGenerateTask(task_id, {
          onProgress: (step) => {
            appendStatus(step === "inpainting" ? "抹除原字中…" : "准备文字区域…");
          },
          onComplete: async (url, _layers, overlay) => {
            try {
              const replaced = await replaceSelectedImageSrc(url);
              if (!replaced) {
                appendError("抹字成功，但更新画布图片失败");
                setBusy(false);
                return;
              }
              if (overlay) {
                const overlaid = overlayTextOnSelectedImage(overlay.text, overlay.bbox, {
                  width: overlay.image_width,
                  height: overlay.image_height,
                });
                if (!overlaid) {
                  appendError("抹字成功，但叠字失败");
                } else {
                  appendStatus(`已将「${region.text}」替换为「${overlay.text}」`);
                }
              }
              appendMessage({
                id: createMessageId(),
                role: "assistant",
                kind: "image",
                imageUrl: url,
                caption: "文字编辑结果",
              });
            } catch (err) {
              appendError(err instanceof Error ? err.message : "回贴失败");
            }
            setBusy(false);
          },
          onError: (msg) => {
            appendError(msg);
            setBusy(false);
          },
        });
      }
    } catch (err) {
      appendError(err instanceof Error ? err.message : "任务失败");
      setBusy(false);
    }
  }

  return (
    <>
      {maskEditorOpen && maskPreviewUrl ? (
        <MaskTool
          imageUrl={maskPreviewUrl}
          onComplete={(mask) => void handleMaskComplete(mask)}
          onCancel={() => {
            setMaskEditorOpen(false);
            setMaskPreviewUrl(null);
          }}
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
