import { API_BASE } from "./theme";
import { connectTaskWebSocket, type DecomposeLayer, type TextEditOverlay } from "./ws";

export function runGenerateTask(
  taskId: string,
  handlers: {
    onProgress?: (step?: string) => void;
    onComplete: (
      imageUrl: string,
      layers?: DecomposeLayer[],
      overlay?: TextEditOverlay,
    ) => void;
    onError: (message: string) => void;
    onReconnect?: (attempt: number) => void;
  },
): () => void {
  let settled = false;

  const handle = connectTaskWebSocket(
    taskId,
    (event) => {
      if (settled) {
        return;
      }

      if (event.type === "progress") {
        handlers.onProgress?.(event.step ?? event.status);
        return;
      }

      if (event.type === "complete") {
        settled = true;
        const layers = event.layers?.map((layer) => ({
          label: layer.label,
          image_url: `${API_BASE}${layer.image_url}`,
        }));
        handlers.onComplete(`${API_BASE}${event.image_url}`, layers, event.overlay);
        return;
      }

      if (event.type === "error") {
        settled = true;
        handlers.onError(event.message);
      }
    },
    undefined,
    {
      onReconnect: (attempt) => {
        handlers.onReconnect?.(attempt);
      },
    },
  );

  return () => {
    settled = true;
    handle.close();
  };
}
