import { describe, expect, it } from "vitest";

import { coverCropRect } from "./layer-paste-bake";

describe("coverCropRect", () => {
  it("center-crops the longer axis when aspects differ (portrait → square)", () => {
    expect(coverCropRect(100, 200, 100, 100)).toEqual({
      sx: 0,
      sy: 50,
      sw: 100,
      sh: 100,
    });
  });

  it("uses the full source when aspects already match", () => {
    expect(coverCropRect(80, 120, 40, 60)).toEqual({
      sx: 0,
      sy: 0,
      sw: 80,
      sh: 120,
    });
  });

  it("center-crops width for landscape into portrait box", () => {
    expect(coverCropRect(200, 100, 50, 100)).toEqual({
      sx: 75,
      sy: 0,
      sw: 50,
      sh: 100,
    });
  });
});
