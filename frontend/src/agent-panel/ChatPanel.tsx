"use client";

import { useState } from "react";

import {
  requestPlan,
  submitInpaint,
  submitTxt2Img,
  type IntentType,
} from "@/lib/api";
import { API_BASE, theme } from "@/lib/theme";
import { connectTaskWebSocket } from "@/lib/ws";

import { TaskStatus } from "./TaskStatus";

function watchTask(
  taskId: string,
  onComplete: (imageUrl: string) => void,
  onError: (message: string) => void,
  setStatus: (status: string) => void,
) {
  connectTaskWebSocket(taskId, (event) => {
    if (event.type === "progress") {
      setStatus("generating…");
    }
    if (event.type === "complete") {
      onComplete(`${API_BASE}${event.image_url}`);
      setStatus("complete");
    }
    if (event.type === "error") {
      onError(event.message);
      setStatus("error");
    }
  });
}

export function ChatPanel() {
  const [message, setMessage] = useState("");
  const [intent, setIntent] = useState<IntentType>("txt2img");
  const [status, setStatus] = useState<string>("idle");
  const [lastImageUrl, setLastImageUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [maskFile, setMaskFile] = useState<File | null>(null);

  async function handleSubmit() {
    if (!message.trim()) return;
    setError(null);
    setLastImageUrl(null);
    setStatus("planning");

    try {
      const plan = await requestPlan({
        user_message: message,
        intent_override: intent,
      });
      setStatus(`planned: ${plan.intent}`);

      if (plan.intent === "txt2img") {
        setStatus("generating");
        const { task_id } = await submitTxt2Img(plan.refined_prompt);
        watchTask(
          task_id,
          setLastImageUrl,
          (msg) => setError(msg),
          setStatus,
        );
        return;
      }

      if (!imageFile || !maskFile) {
        setError("inpaint 需要上传原图和 mask（白区=重绘区域）");
        setStatus("error");
        return;
      }

      setStatus("generating");
      const { task_id } = await submitInpaint({
        image: imageFile,
        mask: maskFile,
        prompt: plan.refined_prompt,
      });
      watchTask(task_id, setLastImageUrl, (msg) => setError(msg), setStatus);
    } catch (err) {
      setError(err instanceof Error ? err.message : "unknown error");
      setStatus("error");
    }
  }

  return (
    <div className="flex h-full flex-col p-4" style={{ color: theme.textPrimary }}>
      <header className="mb-4">
        <h1 className="text-lg font-semibold">InfDrawing</h1>
        <p className="text-sm" style={{ color: theme.textMuted }}>
          AI 创意画布 · 阶段一原型
        </p>
      </header>

      <label className="mb-2 text-sm" style={{ color: theme.textMuted }}>
        Intent
      </label>
      <select
        className="mb-4 rounded-md border px-3 py-2 text-sm"
        style={{
          background: theme.surface,
          borderColor: theme.border,
          color: theme.textPrimary,
        }}
        value={intent}
        onChange={(e) => setIntent(e.target.value as IntentType)}
      >
        <option value="txt2img">txt2img</option>
        <option value="inpaint">inpaint</option>
      </select>

      {intent === "inpaint" ? (
        <div
          className="mb-4 space-y-3 rounded-md border p-3 text-xs"
          style={{ borderColor: theme.border, color: theme.textMuted }}
        >
          <p>inpaint 需要两张 512×512 PNG，尺寸需一致：</p>
          <ul className="list-inside list-disc space-y-1">
            <li>原图：要编辑的图片</li>
            <li>Mask：黑底白区（白色=重绘区域）</li>
          </ul>
          <p>
            测试图可运行{" "}
            <code className="rounded px-1" style={{ background: theme.surface }}>
              scripts/comfyui/make_test_images.py
            </code>
            ，输出在 <code className="rounded px-1">D:\ComfyUI\input\</code>
          </p>
          <label className="block">
            <span className="mb-1 block">原图</span>
            <input
              type="file"
              accept="image/png,image/jpeg"
              className="w-full text-xs"
              onChange={(e) => setImageFile(e.target.files?.[0] ?? null)}
            />
          </label>
          <label className="block">
            <span className="mb-1 block">Mask</span>
            <input
              type="file"
              accept="image/png,image/jpeg"
              className="w-full text-xs"
              onChange={(e) => setMaskFile(e.target.files?.[0] ?? null)}
            />
          </label>
        </div>
      ) : null}

      <textarea
        className="mb-3 min-h-[120px] flex-1 resize-none rounded-md border px-3 py-2 text-sm"
        style={{
          background: theme.surface,
          borderColor: theme.border,
          color: theme.textPrimary,
        }}
        placeholder={
          intent === "inpaint"
            ? "描述重绘区域要变成什么，例如：a bright red apple"
            : "描述你想生成的内容…"
        }
        value={message}
        onChange={(e) => setMessage(e.target.value)}
      />

      <button
        type="button"
        className="rounded-md px-4 py-2 text-sm font-medium text-white"
        style={{ background: theme.accent }}
        onClick={handleSubmit}
      >
        发送
      </button>

      <TaskStatus status={status} error={error} imageUrl={lastImageUrl} />
    </div>
  );
}
