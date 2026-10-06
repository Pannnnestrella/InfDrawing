/** Pending canvas AI requests (context menu → overlay), one slot per kind. */

export type CanvasRequestKind = "generate" | "decompose" | "library-ingest";

export interface CanvasAnchor {
  pageX: number;
  pageY: number;
}

export interface CanvasRequest {
  anchor: CanvasAnchor;
}

type Listener = () => void;

const pending = new Map<CanvasRequestKind, CanvasRequest>();
const listeners = new Set<Listener>();

function notify() {
  listeners.forEach((fn) => fn());
}

export function subscribeCanvasRequests(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function openCanvasRequest(kind: CanvasRequestKind, anchor: CanvasAnchor): void {
  pending.set(kind, { anchor });
  notify();
}

export function consumeCanvasRequest(kind: CanvasRequestKind): CanvasRequest | null {
  const request = pending.get(kind) ?? null;
  pending.delete(kind);
  return request;
}

export function closeCanvasRequest(kind: CanvasRequestKind): void {
  pending.delete(kind);
  notify();
}
