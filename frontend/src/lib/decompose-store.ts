/** Shared state for canvas element decompose flow. */

export interface DecomposeAnchor {
  pageX: number;
  pageY: number;
}

export interface DecomposeRequest {
  anchor: DecomposeAnchor;
}

type Listener = () => void;

let pendingRequest: DecomposeRequest | null = null;
const listeners = new Set<Listener>();

function notify() {
  listeners.forEach((fn) => fn());
}

export function subscribeDecompose(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function openDecomposeRequest(anchor: DecomposeAnchor): void {
  pendingRequest = { anchor };
  notify();
}

export function consumeDecomposeRequest(): DecomposeRequest | null {
  const request = pendingRequest;
  pendingRequest = null;
  return request;
}

export function closeDecomposeRequest(): void {
  pendingRequest = null;
  notify();
}
