import { API_BASE } from "./theme";

export type IntentType = "txt2img" | "inpaint";

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

export async function submitTxt2Img(prompt: string) {
  const body = new FormData();
  body.set("prompt", prompt);
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
