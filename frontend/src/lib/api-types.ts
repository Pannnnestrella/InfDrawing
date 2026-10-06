/** Shared request/response types for the backend API and task events. */

export type IntentType =
  | "txt2img"
  | "inpaint"
  | "image_edit"
  | "decompose"
  | "text_edit";

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
  clarification_required?: boolean;
  clarification_question?: string | null;
  /** Compatibility with earlier API drafts. */
  needs_clarification?: boolean;
  clarification_message?: string | null;
}

export interface AgentRoutingContext {
  image_id?: string | null;
  mask_id?: string | null;
  bbox?: [number, number, number, number] | null;
  new_text?: string | null;
  capabilities?: Record<string, boolean>;
  metadata?: Record<string, unknown>;
}
