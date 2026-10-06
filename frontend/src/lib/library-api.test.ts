import { afterEach, describe, expect, it, vi } from "vitest";

import {
  DuplicateAssetError,
  createLibrary,
  ingestAsset,
  itemsQueryPath,
  listItems,
  patchLibrary,
} from "./library-api";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("library API client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("builds search query strings", () => {
    expect(itemsQueryPath("", "")).toBe("/api/v1/assets/items");
    expect(itemsQueryPath(" 骑士 ", "lib 1")).toBe(
      "/api/v1/assets/items?q=%E9%AA%91%E5%A3%AB&library_id=lib+1",
    );
  });

  it("posts ingest as multipart with provenance and force", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(201, { id: "i1" }));
    vi.stubGlobal("fetch", fetchMock);
    const file = new File(["x"], "a.png", { type: "image/png" });
    await ingestAsset({
      image: file,
      libraryId: "lib",
      libraryPurpose: "可复用部件",
      title: "骑士",
      keywords: "持剑, 全身",
      sourceProject: "骑士demo",
      characterName: "女剑士",
      force: true,
    });
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe("POST");
    expect(init.body).toBeInstanceOf(FormData);
    const form = init.body as FormData;
    expect(form.get("library_id")).toBe("lib");
    expect(form.get("library_purpose")).toBe("可复用部件");
    expect(form.get("title")).toBe("骑士");
    expect(form.get("keywords")).toBe("持剑, 全身");
    expect(form.get("source_project")).toBe("骑士demo");
    expect(form.get("character_name")).toBe("女剑士");
    expect(form.get("force")).toBe("true");
  });

  it("maps duplicate_asset 409 onto DuplicateAssetError", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(409, {
        error: {
          code: "duplicate_asset",
          message: "相同内容已入库：骑士",
          details: { existing_id: "e1", title: "骑士", library_id: "lib" },
        },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const file = new File(["x"], "a.png", { type: "image/png" });
    const error = await ingestAsset({ image: file }).catch((exc: unknown) => exc);
    expect(error).toBeInstanceOf(DuplicateAssetError);
    expect(error).toMatchObject({
      existingId: "e1",
      existingTitle: "骑士",
      libraryId: "lib",
    });
  });

  it("creates and patches library purpose", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(201, { id: "lib", name: "角色", purpose: "部件" }))
      .mockResolvedValueOnce(jsonResponse(200, { id: "lib", name: "角色", purpose: "新用途" }));
    vi.stubGlobal("fetch", fetchMock);
    await createLibrary("角色", "部件");
    const [, createInit] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(createInit.body))).toEqual({ name: "角色", purpose: "部件" });
    await patchLibrary("lib", { purpose: "新用途" });
    const [patchUrl, patchInit] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(patchUrl).toBe("/api/v1/assets/libraries/lib");
    expect(patchInit.method).toBe("PATCH");
    expect(JSON.parse(String(patchInit.body))).toEqual({ purpose: "新用途" });
  });

  it("lists items with encoded query", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, []));
    vi.stubGlobal("fetch", fetchMock);
    await listItems("冷色", "abc");
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      "/api/v1/assets/items?q=%E5%86%B7%E8%89%B2&library_id=abc",
    );
  });
});
