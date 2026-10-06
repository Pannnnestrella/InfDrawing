import { authenticatedFetch } from "./api-client";
import type { TaskEvent } from "./ws";

export interface TaskEventStreamHandle {
  close: () => void;
}

export function parseTaskEventBlock(block: string): TaskEvent | null {
  const data = block
    .replace(/\r/g, "")
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart())
    .join("\n");
  if (!data) return null;
  return JSON.parse(data) as TaskEvent;
}

export function connectTaskEventStream(
  taskId: string,
  onEvent: (event: TaskEvent) => void,
): TaskEventStreamHandle {
  const controller = new AbortController();
  let finished = false;

  void (async () => {
    try {
      const response = await authenticatedFetch(
        `/api/task-events?task_id=${encodeURIComponent(taskId)}`,
        {
          headers: { Accept: "text/event-stream" },
          signal: controller.signal,
        },
      );
      if (!response.ok || !response.body) {
        throw new Error(`任务事件连接失败：${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (!finished) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");

        let boundary = buffer.indexOf("\n\n");
        while (boundary >= 0) {
          const event = parseTaskEventBlock(buffer.slice(0, boundary));
          buffer = buffer.slice(boundary + 2);
          if (event) {
            onEvent(event);
            if (event.type === "complete" || event.type === "error") {
              finished = true;
              controller.abort();
              return;
            }
          }
          boundary = buffer.indexOf("\n\n");
        }
      }

      if (!finished) {
        onEvent({ type: "error", message: "任务事件连接已关闭" });
      }
    } catch (error) {
      if (!controller.signal.aborted && !finished) {
        onEvent({
          type: "error",
          message: error instanceof Error ? error.message : "任务事件连接失败",
        });
      }
    }
  })();

  return {
    close: () => {
      finished = true;
      controller.abort();
    },
  };
}
