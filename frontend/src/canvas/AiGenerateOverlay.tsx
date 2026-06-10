"use client";

import { useEffect, useState } from "react";

import { PromptPopover } from "@/canvas/PromptPopover";
import {
  consumeAiGenerateRequest,
  subscribeAiGenerate,
  type AiGenerateRequest,
} from "@/lib/ai-generate-store";
import { pasteImageUrlToCanvasAt } from "@/lib/canvas-bridge";
import { fetchCapabilities, tierLabel } from "@/lib/capabilities";
import { requestPlan, submitTxt2Img } from "@/lib/api";
import { runGenerateTask } from "@/lib/generate-task";
import { theme } from "@/lib/theme";

export function AiGenerateOverlay() {
  const [request, setRequest] = useState<AiGenerateRequest | null>(null);
  const [status, setStatus] = useState<string>("idle");
  const [error, setError] = useState<string | null>(null);
  const [backendLabel, setBackendLabel] = useState("SD 1.5");

  useEffect(() => {
    const sync = () => {
      const next = consumeAiGenerateRequest();
      if (next) {
        setRequest(next);
        setStatus("idle");
        setError(null);
      }
    };
    sync();
    return subscribeAiGenerate(sync);
  }, []);

  useEffect(() => {
    if (!request) return;
    void fetchCapabilities()
      .then((caps) => {
        const backend = caps.features.txt2img?.backend ?? "sd15";
        const label =
          backend === "flux"
            ? "Flux"
            : backend === "dashscope_api"
              ? "DashScope API"
              : "SD 1.5";
        setBackendLabel(`${label} · ${tierLabel(caps.tier)}`);
      })
      .catch(() => setBackendLabel("SD 1.5"));
  }, [request]);

  function handleClose() {
    setRequest(null);
    setStatus("idle");
    setError(null);
  }

  async function handleSubmit(message: string) {
    if (!request) return;
    setError(null);
    setStatus("planning");

    try {
      const plan = await requestPlan({
        user_message: message,
        intent_override: "txt2img",
      });
      setStatus("generating");
      const { task_id } = await submitTxt2Img(plan.refined_prompt, "auto");
      runGenerateTask(task_id, {
        onProgress: () => setStatus("generating…"),
        onComplete: async (imageUrl) => {
          try {
            const pasted = await pasteImageUrlToCanvasAt(
              imageUrl,
              request.anchor.pageX,
              request.anchor.pageY,
            );
            if (!pasted) {
              setError("生成成功，但回贴画布失败");
            } else {
              handleClose();
            }
          } catch (err) {
            setError(err instanceof Error ? err.message : "回贴失败");
          }
          setStatus("complete");
        },
        onError: (msg) => {
          setError(msg);
          setStatus("error");
        },
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成失败");
      setStatus("error");
    }
  }

  if (!request) return null;

  return (
    <>
      <PromptPopover
        backendLabel={backendLabel}
        onSubmit={(prompt) => void handleSubmit(prompt)}
        onCancel={handleClose}
      />
      {status !== "idle" || error ? (
        <div
          className="pointer-events-none fixed bottom-6 left-6 z-[10001] rounded-md border px-3 py-2 text-xs shadow-lg"
          style={{
            background: theme.surface,
            borderColor: theme.border,
            color: error ? "#f87171" : theme.textMuted,
          }}
        >
          {error ?? status}
        </div>
      ) : null}
    </>
  );
}
