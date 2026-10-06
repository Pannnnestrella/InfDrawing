import { apiFetch } from "./api-client";
import type {
  AgentRoutingContext,
  DetectTextResponse,
  IntentPlan,
  IntentType,
} from "./api-types";

export type {
  DecomposeLayer,
  DetectTextResponse,
  IntentPlan,
  IntentType,
  TextEditOverlay,
  TextRegion,
} from "./api-types";

interface TaskResponse {
  task_id: string;
}

/** POST multipart form data; undefined fields are omitted. */
async function postForm<T>(
  path: string,
  fields: Record<string, string | File | undefined>,
): Promise<T> {
  const body = new FormData();
  for (const [key, value] of Object.entries(fields)) {
    if (value !== undefined) body.set(key, value);
  }
  const response = await apiFetch(path, { method: "POST", body });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `${path} failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function requestPlan(input: {
  user_message: string;
  intent_override?: IntentType;
  context?: AgentRoutingContext;
}): Promise<IntentPlan> {
  const response = await apiFetch("/api/v1/agent/plan", {
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
  return postForm<TaskResponse>("/api/v1/generate/txt2img", { prompt, backend });
}

export async function submitInpaint(input: {
  image: File;
  mask: File;
  prompt: string;
  backend?: string;
}) {
  return postForm<TaskResponse>("/api/v1/generate/inpaint", {
    image: input.image,
    mask: input.mask,
    prompt: input.prompt,
    backend: input.backend ?? "auto",
  });
}

export async function submitImageEdit(input: { image: File; prompt: string }) {
  return postForm<TaskResponse>("/api/v1/generate/image-edit", {
    image: input.image,
    prompt: input.prompt,
  });
}

export async function submitDecompose(image: File, backgroundPrompt?: string) {
  return postForm<TaskResponse>("/api/v1/generate/decompose", {
    image,
    background_prompt: backgroundPrompt || undefined,
  });
}

export async function detectTextRegions(image: File): Promise<DetectTextResponse> {
  return postForm<DetectTextResponse>("/api/v1/vision/detect-text", { image });
}

export async function submitTextEdit(input: {
  image: File;
  bbox: [number, number, number, number];
  newText: string;
}) {
  return postForm<TaskResponse>("/api/v1/generate/text-edit", {
    image: input.image,
    bbox: JSON.stringify(input.bbox),
    new_text: input.newText,
  });
}
