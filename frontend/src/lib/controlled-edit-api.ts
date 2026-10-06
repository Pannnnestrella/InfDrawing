import { apiFetch } from "./api-client";

const BASE = "/api/v1/controlled-edit";

export type EntityStatus = "locked" | "approved" | "editable";
export type VersionStatus = "pending" | "running" | "succeeded" | "failed";
export type PromptStyle = "preserve" | "target_only";
export type ImageProvider = "dashscope" | "openai";

export interface BBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface SceneEntity {
  id: string;
  name: string;
  parent_id: string | null;
  description: string;
  bbox: BBox | null;
  bbox_source: "model" | "manual";
  status: EntityStatus;
  anchor_version_id: string | null;
  anchor_artifact_id: string | null;
}

export interface EditIntent {
  operation: string;
  target_entity_ids: string[];
  new_entity_name: string | null;
  location_hint: string | null;
  change_description: string;
}

export interface EntityPreservation {
  entity_id: string;
  score: number;
  comment: string;
}

export interface VerificationResult {
  target_applied: boolean;
  target_comment: string;
  composition_score: number | null;
  composition_comment: string;
  preserved: EntityPreservation[];
  passed: boolean;
  warnings: string[];
}

export interface EditVersion {
  id: string;
  session_id: string;
  parent_id: string | null;
  status: VersionStatus;
  progress_step: string | null;
  image_artifact_id: string | null;
  width: number | null;
  height: number | null;
  instruction: string | null;
  intent: EditIntent | null;
  compiled_prompt: string | null;
  prompt_style: PromptStyle | null;
  image_provider: ImageProvider | null;
  reference_artifact_ids: string[];
  entities: SceneEntity[];
  verification: VerificationResult | null;
  attempts: number;
  warnings: string[];
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface EditSession {
  id: string;
  owner_key_id: string;
  title: string;
  root_version_id: string | null;
  current_version_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface SessionTree {
  session: EditSession;
  versions: EditVersion[];
}

export interface LockConflictEntity {
  id: string;
  name: string;
}

/** Error carrying the backend's stable `{error: {code, message, details}}` shape. */
export class ControlledEditApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly details: unknown = null,
  ) {
    super(message);
    this.name = "ControlledEditApiError";
  }

  get conflictEntities(): LockConflictEntity[] {
    if (this.code !== "lock_conflict") return [];
    const entities = (this.details as { entities?: LockConflictEntity[] } | null)?.entities;
    return Array.isArray(entities) ? entities : [];
  }
}

async function parseOrThrow<T>(response: Response): Promise<T> {
  if (response.ok) return (await response.json()) as T;
  let code = "http_error";
  let message = `请求失败：${response.status}`;
  let details: unknown = null;
  try {
    const body = (await response.json()) as {
      error?: { code?: string; message?: string; details?: unknown };
    };
    code = body.error?.code ?? code;
    message = body.error?.message ?? message;
    details = body.error?.details ?? null;
  } catch {
    // Non-JSON error bodies keep the generic message.
  }
  if (response.status === 403) message = "当前 API Key 没有「多轮可控编辑」权限（controlled_edit）";
  throw new ControlledEditApiError(message, response.status, code, details);
}

function postJson(path: string, body: unknown): Promise<Response> {
  return apiFetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function createSession(image: File, title: string): Promise<SessionTree> {
  const form = new FormData();
  form.append("image", image);
  form.append("title", title || "Untitled");
  return parseOrThrow(await apiFetch(`${BASE}/sessions`, { method: "POST", body: form }));
}

export async function listSessions(): Promise<EditSession[]> {
  return parseOrThrow(await apiFetch(`${BASE}/sessions`));
}

export async function getSessionTree(sessionId: string): Promise<SessionTree> {
  return parseOrThrow(await apiFetch(`${BASE}/sessions/${encodeURIComponent(sessionId)}`));
}

export async function submitTurn(
  sessionId: string,
  parentVersionId: string,
  instruction: string,
  targetEntityIds: string[] = [],
  options: {
    promptStyle?: PromptStyle;
    imageProvider?: ImageProvider;
  } = {},
): Promise<EditVersion> {
  return parseOrThrow(
    await postJson(`/sessions/${encodeURIComponent(sessionId)}/turns`, {
      parent_version_id: parentVersionId,
      instruction,
      target_entity_ids: targetEntityIds,
      ...(options.promptStyle ? { prompt_style: options.promptStyle } : {}),
      ...(options.imageProvider ? { image_provider: options.imageProvider } : {}),
    }),
  );
}

export async function updateEntityStatus(
  sessionId: string,
  versionId: string,
  entityId: string,
  status: EntityStatus,
): Promise<EditVersion> {
  const path =
    `/sessions/${encodeURIComponent(sessionId)}/versions/${encodeURIComponent(versionId)}` +
    `/entities/${encodeURIComponent(entityId)}/status`;
  return parseOrThrow(await postJson(path, { status }));
}

export async function updateEntityBBox(
  sessionId: string,
  versionId: string,
  entityId: string,
  bbox: BBox,
): Promise<EditVersion> {
  const path =
    `/sessions/${encodeURIComponent(sessionId)}/versions/${encodeURIComponent(versionId)}` +
    `/entities/${encodeURIComponent(entityId)}/bbox`;
  return parseOrThrow(
    await apiFetch(`${BASE}${path}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ bbox }),
    }),
  );
}

export async function checkoutVersion(
  sessionId: string,
  versionId: string,
): Promise<EditSession> {
  return parseOrThrow(
    await postJson(`/sessions/${encodeURIComponent(sessionId)}/checkout`, {
      version_id: versionId,
    }),
  );
}

export async function deleteVersion(
  sessionId: string,
  versionId: string,
): Promise<SessionTree> {
  return parseOrThrow(
    await apiFetch(
      `${BASE}/sessions/${encodeURIComponent(sessionId)}/versions/${encodeURIComponent(versionId)}`,
      { method: "DELETE" },
    ),
  );
}

/** Download an owned artifact through the feature-scoped endpoint as a blob URL. */
export async function fetchArtifactBlobUrl(artifactId: string): Promise<string> {
  const response = await apiFetch(`${BASE}/artifacts/${encodeURIComponent(artifactId)}`);
  if (!response.ok) throw new Error(`读取图片失败：${response.status}`);
  return URL.createObjectURL(await response.blob());
}

export function isVersionBusy(version: EditVersion): boolean {
  return version.status === "pending" || version.status === "running";
}

export const PROGRESS_LABELS: Record<string, string> = {
  queued: "排队中",
  preparing: "准备参考图",
  generating: "生成中",
  retrying: "验收未通过，重试中",
  verifying: "VLM 验收中",
  parsing: "解析新版本实体",
};
