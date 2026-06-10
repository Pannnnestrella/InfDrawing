import { WS_BASE } from "./theme";

export interface DecomposeLayer {
  label: string;
  image_url: string;
}

export interface TextEditOverlay {
  text: string;
  bbox: [number, number, number, number];
  image_width: number;
  image_height: number;
}

export type TaskEvent =
  | { type: "progress"; task_id: string; status?: string; step?: string }
  | {
      type: "complete";
      task_id: string;
      image_url: string;
      layers?: DecomposeLayer[];
      overlay?: TextEditOverlay;
    }
  | { type: "error"; task_id?: string; message: string };

export function connectTaskWebSocket(
  taskId: string,
  onEvent: (event: TaskEvent) => void,
  onClose?: () => void,
): WebSocket {
  const wsBase = WS_BASE.replace(/^http/, "ws");
  const socket = new WebSocket(`${wsBase}/api/v1/ws?task_id=${taskId}`);

  socket.onmessage = (message) => {
    onEvent(JSON.parse(message.data) as TaskEvent);
  };
  socket.onclose = () => onClose?.();
  return socket;
}
