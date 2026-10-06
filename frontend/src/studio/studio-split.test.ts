import { afterEach, describe, expect, it } from "vitest";

import { loadSplitSize, saveSplitSize } from "./studio-split";

describe("studio split storage", () => {
  afterEach(() => {
    sessionStorage.clear();
  });

  it("returns the fallback when nothing is stored", () => {
    expect(loadSplitSize("aside", 320, 220)).toBe(320);
  });

  it("reads a stored size and clamps to min", () => {
    saveSplitSize("aside", 400);
    expect(loadSplitSize("aside", 320, 220)).toBe(400);
    sessionStorage.setItem("infd.cedit.split.tree", "10");
    expect(loadSplitSize("tree", 160, 96)).toBe(96);
  });
});
