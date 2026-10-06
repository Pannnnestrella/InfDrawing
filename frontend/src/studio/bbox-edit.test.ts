import { describe, expect, it } from "vitest";

import { MIN_BBOX_SIDE, applyBBoxDrag, roundBBox } from "./bbox-edit";

const BOX = { x: 0.2, y: 0.3, w: 0.4, h: 0.2 };

describe("applyBBoxDrag", () => {
  it("moves the box and keeps it inside the image", () => {
    const moved = applyBBoxDrag(BOX, "move", 0.1, -0.1);
    expect(moved.x).toBeCloseTo(0.3);
    expect(moved.y).toBeCloseTo(0.2);
    expect([moved.w, moved.h]).toEqual([0.4, 0.2]);
    const pushed = applyBBoxDrag(BOX, "move", 5, 5);
    expect(pushed.x + pushed.w).toBeCloseTo(1);
    expect(pushed.y + pushed.h).toBeCloseTo(1);
    expect(applyBBoxDrag(BOX, "move", -5, -5)).toMatchObject({ x: 0, y: 0 });
  });

  it("resizes from a corner while the opposite corner stays fixed", () => {
    const grown = applyBBoxDrag(BOX, "se", 0.1, 0.1);
    expect(grown.x).toBe(0.2);
    expect(grown.y).toBe(0.3);
    expect(grown.w).toBeCloseTo(0.5);
    expect(grown.h).toBeCloseTo(0.3);

    const nw = applyBBoxDrag(BOX, "nw", -0.1, -0.1);
    expect(nw.x).toBeCloseTo(0.1);
    expect(nw.y).toBeCloseTo(0.2);
    expect(nw.x + nw.w).toBeCloseTo(0.6);
    expect(nw.y + nw.h).toBeCloseTo(0.5);
  });

  it("clamps corners to the image and to the minimum size", () => {
    const outside = applyBBoxDrag(BOX, "ne", 2, -2);
    expect(outside.x + outside.w).toBeCloseTo(1);
    expect(outside.y).toBe(0);

    const collapsed = applyBBoxDrag(BOX, "sw", 1, -1);
    expect(collapsed.w).toBeCloseTo(MIN_BBOX_SIDE);
    expect(collapsed.h).toBeCloseTo(MIN_BBOX_SIDE);
  });
});

describe("roundBBox", () => {
  it("rounds to four decimals", () => {
    expect(roundBBox({ x: 0.123456, y: 0.5, w: 0.333333, h: 0.1 })).toEqual({
      x: 0.1235,
      y: 0.5,
      w: 0.3333,
      h: 0.1,
    });
  });
});
