"use client";

import { useEffect, useRef, useState } from "react";

import {
  closeCanvasRequest,
  consumeCanvasRequest,
  subscribeCanvasRequests,
  type CanvasRequest,
} from "@/lib/canvas-request-store";
import { featureReason, fetchCapabilities } from "@/lib/capabilities";
import {
  pasteDecomposeResult,
  runPipeline,
  submitDecomposeFromSelection,
} from "@/lib/run-pipeline";
import { PipelineToast } from "@/components/PipelineToast";

export function DecomposeOverlay() {
  const [request, setRequest] = useState<CanvasRequest | null>(null);
  const [status, setStatus] = useState<string>("idle");
  const [error, setError] = useState<string | null>(null);
  const runningRef = useRef(false);

  useEffect(() => {
    const sync = () => {
      const next = consumeCanvasRequest("decompose");
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
          runningRef.current = false;
          return;
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "能力探测失败");
        setStatus("error");
        runningRef.current = false;
        return;
      }

      await runPipeline(
        {
          submittedStatus: "提交任务…",
          runningStatus: "处理中…",
          submit: () => submitDecomposeFromSelection(),
          complete: async (result) => {
            await pasteDecomposeResult(result, request!.anchor);
            closeCanvasRequest("decompose");
            setRequest(null);
            setStatus("complete");
          },
        },
        {
          onStatus: setStatus,
          onError: (msg) => {
            setError(msg);
            setStatus("error");
          },
          onSettled: () => {
            runningRef.current = false;
          },
        },
      );
    }

    void run();
  }, [request]);

  // Auto-dismiss the success toast.
  useEffect(() => {
    if (status !== "complete") return;
    const timer = window.setTimeout(() => setStatus("idle"), 2500);
    return () => window.clearTimeout(timer);
  }, [status]);

  const visible = request !== null || status === "complete" || status === "error";
  if (!visible || (status === "idle" && !request)) return null;

  return (
    <PipelineToast
      variant={error ? "error" : status === "complete" ? "success" : "pending"}
      text={error ?? (status === "complete" ? "元素拆解完成" : status)}
    />
  );
}
