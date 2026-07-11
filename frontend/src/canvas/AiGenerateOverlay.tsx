"use client";

import { useEffect, useState } from "react";

import { PromptPopover } from "@/canvas/PromptPopover";
import { requestPlan, submitTxt2Img } from "@/lib/api";
import { pasteImageUrlToCanvasAt } from "@/lib/canvas-bridge";
import {
  consumeCanvasRequest,
  subscribeCanvasRequests,
  type CanvasRequest,
} from "@/lib/canvas-request-store";
import { fetchCapabilities, tierLabel } from "@/lib/capabilities";
import { runPipeline } from "@/lib/run-pipeline";
import { PipelineToast } from "@/components/PipelineToast";

export function AiGenerateOverlay() {
  const [request, setRequest] = useState<CanvasRequest | null>(null);
  const [status, setStatus] = useState<string>("idle");
  const [error, setError] = useState<string | null>(null);
  const [backendLabel, setBackendLabel] = useState("SD 1.5");

  useEffect(() => {
    const sync = () => {
      const next = consumeCanvasRequest("generate");
      if (next) {
        setRequest(next);
        setStatus("idle");
        setError(null);
      }
    };
    sync();
    return subscribeCanvasRequests(sync);
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
    const anchor = request.anchor;
    setError(null);
    setStatus("理解意图中…");

    let refinedPrompt: string;
    try {
      const plan = await requestPlan({
        user_message: message,
        intent_override: "txt2img",
      });
      refinedPrompt = plan.refined_prompt;
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成失败");
      setStatus("error");
      return;
    }

    await runPipeline(
      {
        submittedStatus: "生成中…",
        runningStatus: "生成中…",
        submit: () => submitTxt2Img(refinedPrompt, "auto"),
        complete: async (result) => {
          const pasted = await pasteImageUrlToCanvasAt(
            result.imageUrl,
            anchor.pageX,
            anchor.pageY,
          );
          if (!pasted) {
            throw new Error("生成成功，但回贴画布失败");
          }
          handleClose();
        },
      },
      {
        onStatus: setStatus,
        onError: (msg) => {
          setError(msg);
          setStatus("error");
        },
      },
    );
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
        <PipelineToast
          variant={error ? "error" : "pending"}
          text={error ?? status}
        />
      ) : null}
    </>
  );
}
