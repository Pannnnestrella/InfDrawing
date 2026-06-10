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
  },
): void {
  connectTaskWebSocket(taskId, (event) => {
    if (event.type === "progress") {
      handlers.onProgress?.(event.step);
    }
    if (event.type === "complete") {
      const layers = event.layers?.map((layer) => ({
        label: layer.label,
        image_url: `${API_BASE}${layer.image_url}`,
      }));
      handlers.onComplete(`${API_BASE}${event.image_url}`, layers, event.overlay);
    }
    if (event.type === "error") {
      handlers.onError(event.message);
    }
  });
}
