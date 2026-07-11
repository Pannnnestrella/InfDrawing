/** Shared request/response types for the backend API and task events. */

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

export interface DecomposeLayer {
  label: string;
  image_url: string;
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
