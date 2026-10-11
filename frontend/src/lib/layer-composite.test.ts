import { describe, expect, it } from "vitest";

import {
  computeCompositeBounds,
  duplicateLayerName,
  nextBlankLayerName,
} from "./layer-composite";

describe("computeCompositeBounds", () => {
  it("unions visible rects and skips hidden", () => {
    expect(
      computeCompositeBounds([
        { x: 0, y: 0, w: 100, h: 80 },
        { x: 50, y: 40, w: 100, h: 80, hidden: true },
        { x: 20, y: 10, w: 30, h: 20 },
      ]),
    ).toEqual({ x: 0, y: 0, w: 100, h: 80 });
  });

  it("returns null when nothing is visible", () => {
    expect(
      computeCompositeBounds([{ x: 0, y: 0, w: 10, h: 10, hidden: true }]),
    ).toBeNull();
  });
});

describe("nextBlankLayerName", () => {
  it("picks the first free 图层 N", () => {
    expect(nextBlankLayerName([])).toBe("图层 1");
    expect(nextBlankLayerName(["图层 1", "前景", "图层 2"])).toBe("图层 3");
  });
});

describe("duplicateLayerName", () => {
  it("appends 副本 and increments", () => {
    expect(duplicateLayerName("前景")).toBe("前景 副本");
    expect(duplicateLayerName("前景 副本")).toBe("前景 副本 2");
    expect(duplicateLayerName("前景 副本 2")).toBe("前景 副本 3");
  });
});
