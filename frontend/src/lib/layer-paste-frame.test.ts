import { describe, expect, it } from "vitest";

import { resolveLayerPasteFrame } from "./layer-paste-frame";

describe("resolveLayerPasteFrame", () => {
  it("uses live position only when live size matches the captured frame", () => {
    expect(
      resolveLayerPasteFrame(
        { pageX: 10, pageY: 20, w: 400, h: 600 },
        { pageX: 50, pageY: 60, w: 400, h: 600 },
      ),
    ).toEqual({ pageX: 50, pageY: 60, w: 400, h: 600 });
  });

  it("keeps captured frame when live selection is a different size", () => {
    expect(
      resolveLayerPasteFrame(
        { pageX: 10, pageY: 20, w: 400, h: 600 },
        { pageX: 50, pageY: 60, w: 200, h: 200 },
      ),
    ).toEqual({ pageX: 10, pageY: 20, w: 400, h: 600 });
  });

  it("uses anchor when selection is gone", () => {
    expect(
      resolveLayerPasteFrame({ pageX: 10, pageY: 20, w: 320, h: 480 }, null),
    ).toEqual({ pageX: 10, pageY: 20, w: 320, h: 480 });
  });

  it("falls back to 512 when size missing", () => {
    expect(resolveLayerPasteFrame({ pageX: 0, pageY: 0 }, null)).toEqual({
      pageX: 0,
      pageY: 0,
      w: 512,
      h: 512,
    });
  });
});
