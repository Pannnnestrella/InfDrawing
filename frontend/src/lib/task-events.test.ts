import { afterEach, describe, expect, it, vi } from "vitest";

import { clearSessionApiKey, setSessionApiKey } from "./api-client";
import {
  connectTaskEventStream,
  parseTaskEventBlock,
} from "./task-events";
import type { TaskEvent } from "./ws";

afterEach(() => {
  clearSessionApiKey();
  vi.unstubAllGlobals();
});

describe("parseTaskEventBlock", () => {
  it("parses an SSE data payload", () => {
    expect(
      parseTaskEventBlock(
        'event: complete\nid: 2\ndata: {"type":"complete","task_id":"t1","image_url":"/x.png"}',
      ),
    ).toEqual({
      type: "complete",
      task_id: "t1",
      image_url: "/x.png",
    });
  });
});

describe("connectTaskEventStream", () => {
  it("forwards the session key and completes from streamed events", async () => {
    const payload =
      'data: {"type":"progress","task_id":"t1","step":"queued"}\n\n' +
      'data: {"type":"complete","task_id":"t1","image_url":"/x.png"}\n\n';
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(payload));
        controller.close();
      },
    });
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(body, {
        headers: { "Content-Type": "text/event-stream" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    setSessionApiKey("infd_secret");
    const events: TaskEvent[] = [];

    connectTaskEventStream("t1", (event) => events.push(event));

    await vi.waitFor(() => expect(events).toHaveLength(2));
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(fetchMock.mock.calls[0][0]).toBe("/api/task-events?task_id=t1");
    expect((init.headers as Headers).get("X-API-Key")).toBe("infd_secret");
    expect(events[1].type).toBe("complete");
  });

  it("reports an HTTP failure as a terminal error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(null, { status: 401 })),
    );
    const events: TaskEvent[] = [];

    connectTaskEventStream("t1", (event) => events.push(event));

    await vi.waitFor(() => expect(events).toHaveLength(1));
    expect(events[0]).toEqual({
      type: "error",
      message: "任务事件连接失败：401",
    });
  });
});
