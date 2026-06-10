/** Shared state for canvas AI generate popover. */

export interface AiGenerateAnchor {
  pageX: number;
  pageY: number;
}

export interface AiGenerateRequest {
  anchor: AiGenerateAnchor;
}

type Listener = () => void;

let pendingRequest: AiGenerateRequest | null = null;
const listeners = new Set<Listener>();

function notify() {
  listeners.forEach((fn) => fn());
}

export function subscribeAiGenerate(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function openAiGeneratePopover(anchor: AiGenerateAnchor): void {
  pendingRequest = { anchor };
  notify();
}

export function consumeAiGenerateRequest(): AiGenerateRequest | null {
  const request = pendingRequest;
  pendingRequest = null;
  return request;
}

export function closeAiGeneratePopover(): void {
  pendingRequest = null;
  notify();
}

export function hasAiGenerateRequest(): boolean {
  return pendingRequest !== null;
}
