/** Global canvas toast (quota / billing failures and similar). */

export type CanvasToastVariant = "error" | "success" | "pending";

export interface CanvasToast {
  id: number;
  variant: CanvasToastVariant;
  text: string;
}

type Listener = () => void;

const listeners = new Set<Listener>();
let toast: CanvasToast | null = null;
let nextId = 1;

function notify(): void {
  listeners.forEach((fn) => fn());
}

export function subscribeCanvasToast(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function getCanvasToast(): CanvasToast | null {
  return toast;
}

export function showCanvasToast(text: string, variant: CanvasToastVariant = "error"): void {
  const trimmed = text.trim();
  if (!trimmed) return;
  toast = { id: nextId++, variant, text: trimmed };
  notify();
}

export function dismissCanvasToast(id?: number): void {
  if (!toast) return;
  if (id !== undefined && toast.id !== id) return;
  toast = null;
  notify();
}
