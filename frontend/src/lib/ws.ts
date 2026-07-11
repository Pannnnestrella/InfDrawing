import type { DecomposeLayer, TextEditOverlay } from "./api-types";
import { WS_BASE } from "./config";

export type TaskEvent =
  | { type: "progress"; task_id: string; step?: string }
  | {
      type: "complete";
      task_id: string;
      image_url: string;
      layers?: DecomposeLayer[];
      overlay?: TextEditOverlay;
    }
  | { type: "error"; task_id?: string; message: string };

export interface ConnectTaskWebSocketOptions {
  /** Max reconnect attempts after an unexpected close. Default: 8 */
  maxRetries?: number;
  /** Initial backoff delay in ms. Default: 500 */
  initialDelayMs?: number;
  /** Max backoff delay in ms. Default: 8000 */
  maxDelayMs?: number;
  /** Called before each reconnect attempt (1-based). */
  onReconnect?: (attempt: number) => void;
}

export interface TaskWebSocketHandle {
  close: () => void;
}

function buildTaskWebSocketUrl(taskId: string): string {
  const wsBase = WS_BASE.replace(/^http/, "ws");
  return `${wsBase}/api/v1/ws?task_id=${encodeURIComponent(taskId)}`;
}

function isTerminalEvent(event: TaskEvent): boolean {
  return event.type === "complete" || event.type === "error";
}

/**
 * Subscribe to backend task events with automatic reconnect on unexpected close.
 * Terminal events (complete/error) stop further reconnect attempts.
 */
export function connectTaskWebSocket(
  taskId: string,
  onEvent: (event: TaskEvent) => void,
  onClose?: () => void,
  options?: ConnectTaskWebSocketOptions,
): TaskWebSocketHandle {
  const maxRetries = options?.maxRetries ?? 8;
  const initialDelayMs = options?.initialDelayMs ?? 500;
  const maxDelayMs = options?.maxDelayMs ?? 8000;

  let closedByCaller = false;
  let finished = false;
  let attempt = 0;
  let socket: WebSocket | null = null;
  let retryTimer: ReturnType<typeof setTimeout> | null = null;

  const clearRetryTimer = () => {
    if (retryTimer !== null) {
      clearTimeout(retryTimer);
      retryTimer = null;
    }
  };

  const finish = () => {
    finished = true;
    clearRetryTimer();
    socket?.close();
    socket = null;
    onClose?.();
  };

  const close = () => {
    closedByCaller = true;
    clearRetryTimer();
    socket?.close();
    socket = null;
  };

  const scheduleReconnect = () => {
    if (closedByCaller || finished) {
      return;
    }
    if (attempt >= maxRetries) {
      onEvent({ type: "error", message: "WebSocket connection lost; reconnect failed" });
      finish();
      return;
    }

    const delay = Math.min(initialDelayMs * 2 ** attempt, maxDelayMs);
    attempt += 1;
    options?.onReconnect?.(attempt);
    retryTimer = setTimeout(connect, delay);
  };

  const connect = () => {
    if (closedByCaller || finished) {
      return;
    }

    socket = new WebSocket(buildTaskWebSocketUrl(taskId));

    socket.onmessage = (message) => {
      const event = JSON.parse(message.data) as TaskEvent;
      onEvent(event);
      if (isTerminalEvent(event)) {
        finish();
      }
    };

    socket.onclose = () => {
      socket = null;
      if (closedByCaller || finished) {
        return;
      }
      scheduleReconnect();
    };
  };

  connect();

  return { close };
}
