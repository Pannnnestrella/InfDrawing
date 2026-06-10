import { API_BASE } from "./theme";

import type { CanvasContextSnapshot } from "@/canvas/types";

export type IntentType = "txt2img" | "inpaint" | "decompose" | "text_edit";

export interface TextRegion {
  text: string;
  bbox: [number, number, number, number];
  confidence: number;
}

export interface DetectTextResponse {
  regions: TextRegion[];
  image_width: number;
  image_height: number;
}

export interface TextEditOverlay {
  text: string;
  bbox: [number, number, number, number];
  image_width: number;
  image_height: number;
}

export interface IntentPlan {
  intent: IntentType;
  refined_prompt: string;
  negative_prompt: string;
  target_tool: string;
  params: Record<string, unknown>;
  confidence: number;
  reasoning?: string | null;
}

export async function requestPlan(input: {
  user_message: string;
  intent_override?: IntentType;
  context?: CanvasContextSnapshot;
}) {
  const response = await fetch(`${API_BASE}/api/v1/agent/plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    throw new Error(`plan failed: ${response.status}`);
  }
  const data = (await response.json()) as { plan: IntentPlan };
  return data.plan;
}

export async function submitTxt2Img(prompt: string, backend: string = "auto") {
  const body = new FormData();
  body.set("prompt", prompt);
  body.set("backend", backend);
  const response = await fetch(`${API_BASE}/api/v1/generate/txt2img`, {
    method: "POST",
    body,
  });
  if (!response.ok) {
    throw new Error(`txt2img failed: ${response.status}`);
  }
  return (await response.json()) as { task_id: string };
}

export async function submitInpaint(input: {
  image: File;
  mask: File;
  prompt: string;
}) {
  const body = new FormData();
  body.set("image", input.image);
  body.set("mask", input.mask);
  body.set("prompt", input.prompt);
  const response = await fetch(`${API_BASE}/api/v1/generate/inpaint`, {
    method: "POST",
    body,
  });
  if (!response.ok) {
    throw new Error(`inpaint failed: ${response.status}`);
  }
  return (await response.json()) as { task_id: string };
}

export async function submitDecompose(image: File, backgroundPrompt?: string) {
  const body = new FormData();
  body.set("image", image);
  if (backgroundPrompt) {
    body.set("background_prompt", backgroundPrompt);
  }
  const response = await fetch(`${API_BASE}/api/v1/generate/decompose`, {
    method: "POST",
    body,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `decompose failed: ${response.status}`);
  }
  return (await response.json()) as { task_id: string };
}

export async function detectTextRegions(image: File): Promise<DetectTextResponse> {
  const body = new FormData();
  body.set("image", image);
  const response = await fetch(`${API_BASE}/api/v1/vision/detect-text`, {
    method: "POST",
    body,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `detect-text failed: ${response.status}`);
  }
  return (await response.json()) as DetectTextResponse;
}

export async function submitTextEdit(input: {
  image: File;
  bbox: [number, number, number, number];
  newText: string;
}) {
  const body = new FormData();
  body.set("image", input.image);
  body.set("bbox", JSON.stringify(input.bbox));
  body.set("new_text", input.newText);
  const response = await fetch(`${API_BASE}/api/v1/generate/text-edit`, {
    method: "POST",
    body,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `text-edit failed: ${response.status}`);
  }
  return (await response.json()) as { task_id: string };
}
