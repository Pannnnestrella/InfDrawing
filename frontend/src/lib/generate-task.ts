import type { DecomposeLayer, TextEditOverlay } from "./api-types";
import { fetchApiArtifactUrl, getSessionApiKey } from "./api-client";
import { connectTaskEventStream } from "./task-events";
import { connectTaskWebSocket, type TaskEvent } from "./ws";

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

  const onEvent = (event: TaskEvent) => {
    if (settled) return;

    if (event.type === "progress") {
      handlers.onProgress?.(event.step);
      return;
    }

    if (event.type === "complete") {
      settled = true;
      void (async () => {
        try {
          const [imageUrl, layers] = await Promise.all([
            fetchApiArtifactUrl(event.image_url),
            event.layers
              ? Promise.all(
                  event.layers.map(async (layer) => ({
                    label: layer.label,
                    image_url: await fetchApiArtifactUrl(layer.image_url),
                  })),
                )
              : undefined,
          ]);
          handlers.onComplete(imageUrl, layers, event.overlay);
        } catch (error) {
          handlers.onError(
            error instanceof Error ? error.message : "读取生成结果失败",
          );
        }
      })();
      return;
    }

    if (event.type === "error") {
      settled = true;
      handlers.onError(event.message);
    }
  };

  const handle = getSessionApiKey()
    ? connectTaskEventStream(taskId, onEvent)
    : connectTaskWebSocket(taskId, onEvent, undefined, {
        onReconnect: (attempt) => {
          handlers.onReconnect?.(attempt);
        },
      });

  return () => {
    settled = true;
    handle.close();
  };
}
