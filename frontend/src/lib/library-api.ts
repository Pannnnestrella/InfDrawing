import { apiFetch } from "./api-client";

const BASE = "/api/v1/assets";

export type CaptionStatus = "ok" | "caption_failed";

export interface AssetLibrary {
  id: string;
  owner_key_id: string;
  name: string;
  purpose: string;
  created_at: string;
  updated_at: string;
}

export interface AssetItem {
  id: string;
  owner_key_id: string;
  library_id: string;
  artifact_id: string;
  title: string;
  objects: string[];
  tags: string[];
  keywords: string[];
  description: string;
  style: string;
  source_project: string;
  character_name: string;
  content_sha256: string;
  asset_type: string;
  view: string;
  genre: string;
  background: string;
  pose: string;
  palette: string[];
  materials: string[];
  caption_status: CaptionStatus;
  caption_error: string | null;
  shape_feat: number[] | null;
  created_at: string;
  updated_at: string;
}

export class AssetLibraryApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "AssetLibraryApiError";
  }
}

export class DuplicateAssetError extends AssetLibraryApiError {
  constructor(
    message: string,
    readonly existingId: string,
    readonly existingTitle: string,
    readonly libraryId: string,
  ) {
    super(message, 409);
    this.name = "DuplicateAssetError";
  }
}

type ErrorBody = {
  error?: {
    code?: string;
    message?: string;
    details?: { existing_id?: string; title?: string; library_id?: string };
  };
  detail?: string;
};

async function parseOrThrow<T>(response: Response): Promise<T> {
  if (response.status === 204) return undefined as T;
  let body: ErrorBody | null = null;
  try {
    body = (await response.json()) as ErrorBody;
  } catch {
    body = null;
  }
  if (response.ok) return body as T;
  if (response.status === 409 && body?.error?.code === "duplicate_asset") {
    const details = body.error.details ?? {};
    throw new DuplicateAssetError(
      body.error.message ?? "相同内容已入库",
      details.existing_id ?? "",
      details.title ?? "",
      details.library_id ?? "",
    );
  }
  let message = `请求失败：${response.status}`;
  message = body?.error?.message ?? body?.detail ?? message;
  if (response.status === 403) message = "当前 API Key 没有「素材库」权限（assets）";
  throw new AssetLibraryApiError(message, response.status);
}

export async function listLibraries(): Promise<AssetLibrary[]> {
  return parseOrThrow(await apiFetch(`${BASE}/libraries`));
}

export async function createLibrary(name: string, purpose = ""): Promise<AssetLibrary> {
  return parseOrThrow(
    await apiFetch(`${BASE}/libraries`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, purpose }),
    }),
  );
}

export async function patchLibrary(
  libraryId: string,
  body: Partial<Pick<AssetLibrary, "name" | "purpose">>,
): Promise<AssetLibrary> {
  return parseOrThrow(
    await apiFetch(`${BASE}/libraries/${encodeURIComponent(libraryId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function ingestAsset(options: {
  image: File;
  libraryId?: string;
  libraryName?: string;
  libraryPurpose?: string;
  title?: string;
  keywords?: string;
  sourceProject?: string;
  characterName?: string;
  force?: boolean;
}): Promise<AssetItem> {
  const form = new FormData();
  form.append("image", options.image);
  form.append("library_id", options.libraryId ?? "");
  form.append("library_name", options.libraryName ?? "");
  form.append("library_purpose", options.libraryPurpose ?? "");
  form.append("title", options.title ?? "");
  form.append("keywords", options.keywords ?? "");
  form.append("source_project", options.sourceProject ?? "");
  form.append("character_name", options.characterName ?? "");
  form.append("force", options.force ? "true" : "");
  return parseOrThrow(await apiFetch(`${BASE}/items`, { method: "POST", body: form }));
}

export function itemsQueryPath(query: string, libraryId: string): string {
  const params = new URLSearchParams();
  if (query.trim()) params.set("q", query.trim());
  if (libraryId.trim()) params.set("library_id", libraryId.trim());
  const suffix = params.toString();
  return suffix ? `${BASE}/items?${suffix}` : `${BASE}/items`;
}

export async function listItems(query = "", libraryId = ""): Promise<AssetItem[]> {
  return parseOrThrow(await apiFetch(itemsQueryPath(query, libraryId)));
}

export async function patchItem(
  itemId: string,
  body: Partial<
    Pick<
      AssetItem,
      | "library_id"
      | "title"
      | "objects"
      | "tags"
      | "keywords"
      | "description"
      | "style"
      | "source_project"
      | "character_name"
      | "asset_type"
      | "view"
      | "genre"
      | "background"
      | "pose"
      | "palette"
      | "materials"
    >
  >,
): Promise<AssetItem> {
  return parseOrThrow(
    await apiFetch(`${BASE}/items/${encodeURIComponent(itemId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function deleteItem(itemId: string): Promise<void> {
  await parseOrThrow(await apiFetch(`${BASE}/items/${encodeURIComponent(itemId)}`, { method: "DELETE" }));
}

export async function recaptionItem(itemId: string): Promise<AssetItem> {
  return parseOrThrow(
    await apiFetch(`${BASE}/items/${encodeURIComponent(itemId)}/recaption`, { method: "POST" }),
  );
}

export async function fetchLibraryArtifactUrl(artifactId: string): Promise<string> {
  const response = await apiFetch(`${BASE}/artifacts/${encodeURIComponent(artifactId)}`);
  if (!response.ok) throw new Error(`读取素材失败：${response.status}`);
  return URL.createObjectURL(await response.blob());
}
