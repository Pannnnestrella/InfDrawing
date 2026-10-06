import { afterEach, describe, expect, it, vi } from "vitest";

import { toTldrawCompatibleSrc } from "@/lib/tldraw-asset-src";

describe("toTldrawCompatibleSrc", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("keeps data and http(s) urls", async () => {
    await expect(toTldrawCompatibleSrc("data:image/png;base64,aaa")).resolves.toBe(
      "data:image/png;base64,aaa",
    );
    await expect(toTldrawCompatibleSrc("https://example.com/a.png")).resolves.toBe(
      "https://example.com/a.png",
    );
  });

  it("absolutizes root-relative urls", async () => {
    vi.stubGlobal("window", { location: { origin: "http://127.0.0.1:3000" } });
    await expect(toTldrawCompatibleSrc("/api/v1/files/outputs/x.png")).resolves.toBe(
      "http://127.0.0.1:3000/api/v1/files/outputs/x.png",
    );
  });

  it("converts blob urls to data urls", async () => {
    const blob = new Blob([Uint8Array.from([137, 80, 78, 71])], {
      type: "image/png",
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        blob: async () => blob,
      })),
    );

    const result = await toTldrawCompatibleSrc("blob:http://127.0.0.1:3000/abc");
    expect(result.startsWith("data:image/png;base64,")).toBe(true);
  });
});

