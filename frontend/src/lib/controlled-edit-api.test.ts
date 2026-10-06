import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ControlledEditApiError,
  deleteVersion,
  submitTurn,
  updateEntityStatus,
} from "./controlled-edit-api";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("controlled edit API client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("posts turns as JSON to the session endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(202, { id: "v2" }));
    vi.stubGlobal("fetch", fetchMock);

    const version = await submitTurn("s 1", "v1", "add a hat");

    expect(version).toEqual({ id: "v2" });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/v1/controlled-edit/sessions/s%201/turns");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      parent_version_id: "v1",
      instruction: "add a hat",
      target_entity_ids: [],
    });
  });

  it("includes clicked target entity ids", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(202, { id: "v2" }));
    vi.stubGlobal("fetch", fetchMock);
    await submitTurn("s", "v1", "换剑", ["character.sword"]);
    expect(JSON.parse((fetchMock.mock.calls[0] as [string, RequestInit])[1].body as string)).toEqual({
      parent_version_id: "v1",
      instruction: "换剑",
      target_entity_ids: ["character.sword"],
    });
  });

  it("includes prompt style and image provider when set", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(202, { id: "v2" }));
    vi.stubGlobal("fetch", fetchMock);
    await submitTurn("s", "v1", "换剑", [], {
      promptStyle: "target_only",
      imageProvider: "openai",
    });
    expect(JSON.parse((fetchMock.mock.calls[0] as [string, RequestInit])[1].body as string)).toEqual({
      parent_version_id: "v1",
      instruction: "换剑",
      target_entity_ids: [],
      prompt_style: "target_only",
      image_provider: "openai",
    });
  });

  it("exposes lock conflict entities", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(409, {
          error: {
            code: "lock_conflict",
            message: "locked",
            details: { entities: [{ id: "character.face", name: "Face" }] },
          },
        }),
      ),
    );

    const error = await submitTurn("s", "v", "zombie face").catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ControlledEditApiError);
    const apiError = error as ControlledEditApiError;
    expect(apiError.status).toBe(409);
    expect(apiError.conflictEntities).toEqual([{ id: "character.face", name: "Face" }]);
  });

  it("deletes a version with DELETE", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, { session: { id: "s" }, versions: [{ id: "v1" }] }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const tree = await deleteVersion("s 1", "v 9");
    expect(tree.versions).toEqual([{ id: "v1" }]);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/v1/controlled-edit/sessions/s%201/versions/v%209");
    expect(init.method).toBe("DELETE");
  });

  it("explains missing scope on 403", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(403, { error: { code: "http_error", message: "insufficient scope" } }),
      ),
    );

    await expect(updateEntityStatus("s", "v", "e", "locked")).rejects.toThrow("controlled_edit");
  });

  it("returns no conflict entities for other errors", () => {
    const error = new ControlledEditApiError("x", 502, "http_error", { entities: [{}] });
    expect(error.conflictEntities).toEqual([]);
  });
});
