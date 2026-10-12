import { apiFetch } from "./api-client";

const BASE = "/api/v1/controlled-edit";

export type WorkflowNodeType = "input" | "edit" | "condition" | "merge" | "output";
export type EdgeKind = "default" | "pass" | "fail";
export type WorkflowRunStatus =
  | "pending"
  | "running"
  | "waiting_manual"
  | "succeeded"
  | "failed";

export interface EditNodeConfig {
  instruction: string;
  lock_roles: string[];
  target_roles: string[];
  prompt_style?: "preserve" | "target_only" | null;
  image_provider?: "dashscope" | "openai" | null;
  image_model?: string | null;
}

export interface ConditionNodeConfig {
  kind: "target_applied" | "locked_score" | "entity_role_exists" | "manual";
  min_locked_score?: number;
  role?: string | null;
}

export interface MergeNodeConfig {
  mode: "multi_ref" | "select_best";
}

export interface WorkflowNode {
  id: string;
  type: WorkflowNodeType;
  label: string;
  position: { x: number; y: number };
  edit?: EditNodeConfig | null;
  condition?: ConditionNodeConfig | null;
  merge?: MergeNodeConfig | null;
}

export interface WorkflowEdge {
  id: string;
  source: string;
  target: string;
  kind: EdgeKind;
}

export interface EditWorkflow {
  id: string;
  owner_key_id: string;
  title: string;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  source_session_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkflowRun {
  id: string;
  workflow_id: string;
  owner_key_id: string;
  session_id: string | null;
  status: WorkflowRunStatus;
  node_version_map: Record<string, string>;
  waiting_node_id: string | null;
  output_version_ids: string[];
  error: string | null;
  warnings: string[];
  created_at: string;
  updated_at: string;
}

async function parseOrThrow<T>(response: Response): Promise<T> {
  if (response.ok) {
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }
  let message = `请求失败：${response.status}`;
  try {
    const body = (await response.json()) as { detail?: string; error?: { message?: string } };
    message = body.error?.message ?? (typeof body.detail === "string" ? body.detail : message);
  } catch {
    // keep generic
  }
  throw new Error(message);
}

export async function listWorkflows(): Promise<EditWorkflow[]> {
  return parseOrThrow(await apiFetch(`${BASE}/workflows`));
}

export async function getWorkflow(workflowId: string): Promise<EditWorkflow> {
  return parseOrThrow(await apiFetch(`${BASE}/workflows/${encodeURIComponent(workflowId)}`));
}

export async function createWorkflow(body: {
  title: string;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  source_session_id?: string | null;
}): Promise<EditWorkflow> {
  return parseOrThrow(
    await apiFetch(`${BASE}/workflows`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function updateWorkflow(
  workflowId: string,
  body: { title?: string; nodes?: WorkflowNode[]; edges?: WorkflowEdge[] },
): Promise<EditWorkflow> {
  return parseOrThrow(
    await apiFetch(`${BASE}/workflows/${encodeURIComponent(workflowId)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function deleteWorkflow(workflowId: string): Promise<void> {
  await parseOrThrow(
    await apiFetch(`${BASE}/workflows/${encodeURIComponent(workflowId)}`, {
      method: "DELETE",
    }),
  );
}

export async function startWorkflowRun(
  workflowId: string,
  image: File,
  title = "",
): Promise<WorkflowRun> {
  const form = new FormData();
  form.append("image", image);
  if (title) form.append("title", title);
  return parseOrThrow(
    await apiFetch(`${BASE}/workflows/${encodeURIComponent(workflowId)}/runs`, {
      method: "POST",
      body: form,
    }),
  );
}

export async function getWorkflowRun(runId: string): Promise<WorkflowRun> {
  return parseOrThrow(await apiFetch(`${BASE}/workflow-runs/${encodeURIComponent(runId)}`));
}

export async function resumeWorkflowRun(runId: string, passed = true): Promise<WorkflowRun> {
  return parseOrThrow(
    await apiFetch(`${BASE}/workflow-runs/${encodeURIComponent(runId)}/resume`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ passed }),
    }),
  );
}
