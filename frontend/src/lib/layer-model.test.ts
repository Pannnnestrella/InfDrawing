import { describe, expect, it } from "vitest";

import {
  layerReorderAvailability,
  mergeLayerMeta,
  readLayerMeta,
  resolveLayerName,
  shapeVisibilityFromMeta,
  sortByIndexTopFirst,
} from "./layer-model";

describe("readLayerMeta / mergeLayerMeta", () => {
  it("reads known keys and ignores junk", () => {
    expect(
      readLayerMeta({
        layerName: " 前景 ",
        hidden: true,
        blendMode: "multiply",
        groupId: "g1",
        other: 1,
      }),
    ).toEqual({
      layerName: "前景",
      hidden: true,
      blendMode: "multiply",
      groupId: "g1",
    });
  });

  it("merges without dropping unknown meta keys", () => {
    const merged = mergeLayerMeta(
      { layerName: "A", customFlag: true, hidden: true },
      { layerName: "B", hidden: false },
    );
    expect(merged).toEqual({ layerName: "B", customFlag: true, hidden: false });
  });

  it("unhides by writing hidden:false (tldraw meta merge cannot delete keys)", () => {
    expect(mergeLayerMeta({ hidden: true, layerName: "X" }, { hidden: false })).toEqual({
      layerName: "X",
      hidden: false,
    });
  });

  it("survives tldraw-style shallow meta merge on hide then show", () => {
    let stored: Record<string, unknown> = { layerName: "前景" };
    stored = { ...stored, ...mergeLayerMeta(stored, { hidden: true }) };
    expect(shapeVisibilityFromMeta(stored)).toBe("hidden");

    stored = { ...stored, ...mergeLayerMeta(stored, { hidden: false }) };
    expect(stored.hidden).toBe(false);
    expect(shapeVisibilityFromMeta(stored)).toBe("inherit");
  });

  it("clears optional fields when patched empty", () => {
    expect(mergeLayerMeta({ layerName: "X", blendMode: "screen" }, { layerName: "" })).toEqual({
      blendMode: "screen",
    });
  });
});

describe("resolveLayerName", () => {
  it("prefers meta, then asset stem, then fallback", () => {
    expect(resolveLayerName({ layerName: "前景" }, "fg.png", 1)).toBe("前景");
    expect(resolveLayerName({}, "background.png", 1)).toBe("background");
    expect(resolveLayerName({}, null, 3)).toBe("图层 3");
  });
});

describe("sortByIndexTopFirst", () => {
  it("lists higher index first", () => {
    const sorted = sortByIndexTopFirst([
      { id: "a", index: "a1" },
      { id: "b", index: "a3" },
      { id: "c", index: "a2" },
    ]);
    expect(sorted.map((s) => s.id)).toEqual(["b", "c", "a"]);
  });
});

describe("layerReorderAvailability", () => {
  it("disables all moves for a single layer", () => {
    expect(layerReorderAvailability(0, 1)).toEqual({
      up: false,
      down: false,
      front: false,
      back: false,
    });
  });

  it("enables down/back only for the top layer", () => {
    expect(layerReorderAvailability(0, 3)).toEqual({
      up: false,
      front: false,
      down: true,
      back: true,
    });
  });
});

describe("shapeVisibilityFromMeta", () => {
  it("maps meta.hidden to tldraw visibility tokens", () => {
    expect(shapeVisibilityFromMeta({ hidden: true })).toBe("hidden");
    expect(shapeVisibilityFromMeta({ hidden: false })).toBe("inherit");
    expect(shapeVisibilityFromMeta({})).toBe("inherit");
    expect(shapeVisibilityFromMeta(undefined)).toBe("inherit");
  });
});
