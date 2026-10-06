import WebSocket, { type RawData } from "ws";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const encoder = new TextEncoder();

function backendTaskUrl(taskId: string): URL {
  const backendUrl = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";
  const url = new URL("/api/v1/ws", backendUrl);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.searchParams.set("task_id", taskId);
  return url;
}

export async function GET(request: Request): Promise<Response> {
  const taskId = new URL(request.url).searchParams.get("task_id")?.trim();
  if (!taskId) {
    return Response.json({ detail: "missing task_id" }, { status: 400 });
  }

  const apiKey = request.headers.get("X-API-Key")?.trim();
  const socket = new WebSocket(backendTaskUrl(taskId), {
    headers: apiKey ? { "X-API-Key": apiKey } : undefined,
  });
  let cancelled = false;

  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      let settled = false;

      const closeStream = () => {
        if (settled || cancelled) return;
        settled = true;
        controller.close();
      };

      const sendEvent = (event: unknown) => {
        if (settled || cancelled) return;
        controller.enqueue(
          encoder.encode(`data: ${JSON.stringify(event)}\n\n`),
        );
      };

      const fail = (message: string) => {
        if (settled || cancelled) return;
        sendEvent({ type: "error", task_id: taskId, message });
        closeStream();
        socket.close();
      };

      socket.on("message", (data: RawData) => {
        if (settled) return;
        try {
          const event = JSON.parse(data.toString()) as { type?: string };
          sendEvent(event);
          if (event.type === "complete" || event.type === "error") {
            closeStream();
            socket.close();
          }
        } catch {
          fail("后端返回了无效的任务事件");
        }
      });

      socket.on("error", () => fail("无法连接任务事件服务"));
      socket.on("close", () => {
        if (!settled) fail("任务事件服务提前关闭");
      });

      request.signal.addEventListener(
        "abort",
        () => {
          closeStream();
          cancelled = true;
          socket.close();
        },
        { once: true },
      );
    },
    cancel() {
      cancelled = true;
      socket.close();
    },
  });

  return new Response(stream, {
    headers: {
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "Content-Type": "text/event-stream; charset=utf-8",
    },
  });
}
