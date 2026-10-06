import { API_BASE } from "./config";

const API_KEY_STORAGE_KEY = "infd.api-key";
const API_KEY_CHANGE_EVENT = "infd:api-key-change";

function browserSessionStorage(): Storage | null {
  return typeof window === "undefined" ? null : window.sessionStorage;
}

export function getSessionApiKey(): string | null {
  const value = browserSessionStorage()?.getItem(API_KEY_STORAGE_KEY)?.trim();
  return value || null;
}

export function setSessionApiKey(apiKey: string): void {
  const storage = browserSessionStorage();
  if (!storage) return;
  const value = apiKey.trim();
  if (value) {
    storage.setItem(API_KEY_STORAGE_KEY, value);
  } else {
    storage.removeItem(API_KEY_STORAGE_KEY);
  }
  window.dispatchEvent(new Event(API_KEY_CHANGE_EVENT));
}

export function clearSessionApiKey(): void {
  setSessionApiKey("");
}

export function subscribeSessionApiKey(listener: () => void): () => void {
  if (typeof window === "undefined") return () => undefined;
  window.addEventListener(API_KEY_CHANGE_EVENT, listener);
  return () => window.removeEventListener(API_KEY_CHANGE_EVENT, listener);
}

export function withApiKeyHeaders(headers?: HeadersInit): Headers {
  const nextHeaders = new Headers(headers);
  const apiKey = getSessionApiKey();
  if (apiKey) nextHeaders.set("X-API-Key", apiKey);
  return nextHeaders;
}

export function authenticatedFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
): Promise<Response> {
  return fetch(input, { ...init, headers: withApiKeyHeaders(init.headers) });
}

export function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  return authenticatedFetch(`${API_BASE}${path}`, init);
}

export async function fetchApiArtifactUrl(path: string): Promise<string> {
  if (path.startsWith("blob:") || path.startsWith("data:")) return path;
  const url = /^https?:\/\//.test(path) ? path : `${API_BASE}${path}`;
  const response = await authenticatedFetch(url);
  if (!response.ok) {
    throw new Error(`读取生成结果失败：${response.status}`);
  }
  return URL.createObjectURL(await response.blob());
}
