import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ControlledEditApiError,
  deleteSession,
  deleteVersion,
  renameSession,
  renameVersion,
  submitTurn,
  updateEntityStatus,
  versionDisplayName,
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

  it("marks a confirmed source mask as an explicit local turn", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(202, { id: "local" }));
    vi.stubGlobal("fetch", fetchMock);
    await submitTurn("s", "v1", "recolor", [], {
      imageProvider: "dashscope",
      maskArtifactId: "mask-v1",
    });
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toMatchObject({
      parent_version_id: "v1",
      edit_mode: "local",
      mask_artifact_id: "mask-v1",
      image_provider: "dashscope",
    });
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
      imageProvider: "dashscope",
      imageModel: "qwen-image-2.1-pro",
    });
    expect(JSON.parse((fetchMock.mock.calls[0] as [string, RequestInit])[1].body as string)).toEqual({
      parent_version_id: "v1",
      instruction: "换剑",
      target_entity_ids: [],
      prompt_style: "target_only",
      image_provider: "dashscope",
      image_model: "qwen-image-2.1-pro",
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

  it("renames a version with PATCH", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { id: "v1", title: "开场" }));
    vi.stubGlobal("fetch", fetchMock);
    const version = await renameVersion("s 1", "v 9", "开场");
    expect(version.title).toBe("开场");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/v1/controlled-edit/sessions/s%201/versions/v%209");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body as string)).toEqual({ title: "开场" });
  });

  it("renames and deletes a session", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(200, { id: "s", title: "新名" }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(renameSession("s 1", "新名")).resolves.toMatchObject({ title: "新名" });
    await expect(deleteSession("s 1")).resolves.toBeUndefined();
    expect((fetchMock.mock.calls[0] as [string, RequestInit])[1].method).toBe("PATCH");
    expect((fetchMock.mock.calls[1] as [string, RequestInit])[0]).toBe(
      "/api/v1/controlled-edit/sessions/s%201",
    );
    expect((fetchMock.mock.calls[1] as [string, RequestInit])[1].method).toBe("DELETE");
  });

  it("falls back version display names", () => {
    expect(versionDisplayName({ title: "A", instruction: "long" } as never, true)).toBe("A");
    expect(versionDisplayName({ title: null, instruction: null } as never, true)).toBe("原图");
    expect(
      versionDisplayName(
        { title: null, instruction: "abcdefghijklmnopqrstuvwxyz" } as never,
        false,
      ),
    ).toBe("abcdefghijklmnop…");
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
