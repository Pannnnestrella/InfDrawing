"use client";

import { useEffect, useRef, useState } from "react";

import {
  consumeDecomposeRequest,
  closeDecomposeRequest,
  subscribeDecompose,
  type DecomposeRequest,
} from "@/lib/decompose-store";
import {
  exportSelectedImageFile,
  pasteLayersToCanvas,
} from "@/lib/canvas-bridge";
import { featureReason, fetchCapabilities } from "@/lib/capabilities";
import { submitDecompose } from "@/lib/api";
import { runGenerateTask } from "@/lib/generate-task";
import { theme } from "@/lib/theme";

const STEP_LABELS: Record<string, string> = {
  segmenting: "分割主体…",
  extracting: "提取前景层…",
  inpainting: "补全背景…",
};

export function DecomposeOverlay() {
  const [request, setRequest] = useState<DecomposeRequest | null>(null);
  const [status, setStatus] = useState<string>("idle");
  const [error, setError] = useState<string | null>(null);
  const runningRef = useRef(false);

  useEffect(() => {
    const sync = () => {
      const next = consumeDecomposeRequest();
      if (next) {
        setRequest(next);
        setStatus("idle");
        setError(null);
      }
    };
    sync();
    return subscribeDecompose(sync);
  }, []);

  useEffect(() => {
    if (!request || runningRef.current) return;
    runningRef.current = true;

    async function run() {
      setError(null);
      setStatus("检查能力…");

      try {
        const caps = await fetchCapabilities();
        const reason = featureReason(caps, "decompose");
        if (reason) {
          setError(reason);
          setStatus("error");
          return;
        }

        const imageFile = await exportSelectedImageFile();
        if (!imageFile) {
          setError("请先在画布上选中一张图片");
          setStatus("error");
          return;
        }

        setStatus("提交任务…");
        const { task_id } = await submitDecompose(imageFile);
        runGenerateTask(task_id, {
          onProgress: (step) => setStatus(STEP_LABELS[step ?? ""] ?? "处理中…"),
          onComplete: async (_imageUrl, layers) => {
            try {
              if (!layers?.length) {
                setError("未收到图层数据");
                setStatus("error");
                return;
              }
              const pasted = await pasteLayersToCanvas(layers, request!.anchor);
              if (!pasted) {
                setError("拆解成功，但回贴画布失败");
                setStatus("error");
                return;
              }
              closeDecomposeRequest();
              setRequest(null);
              setStatus("complete");
            } catch (err) {
              setError(err instanceof Error ? err.message : "回贴失败");
              setStatus("error");
            }
          },
          onError: (msg) => {
            setError(msg);
            setStatus("error");
          },
        });
      } catch (err) {
        setError(err instanceof Error ? err.message : "元素拆解失败");
        setStatus("error");
      } finally {
        runningRef.current = false;
      }
    }

    void run();
  }, [request]);

  if (!request && status === "idle") return null;

  const visible = request !== null || status === "complete" || status === "error";

  if (!visible) return null;

  return (
    <div
      className="pointer-events-none fixed bottom-6 left-6 z-[10001] rounded-md border px-3 py-2 text-xs shadow-lg"
      style={{
        background: theme.surface,
        borderColor: theme.border,
        color: error ? "#f87171" : theme.textMuted,
      }}
    >
      {error ?? (status === "complete" ? "元素拆解完成" : status)}
    </div>
  );
}
