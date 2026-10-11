import { describe, expect, it } from "vitest";

import {
  isLayerPanelOpen,
  setLayerPanelOpen,
  subscribeLayerPanel,
} from "./layer-panel-store";

describe("layer-panel-store", () => {
  it("toggles open state and notifies subscribers", () => {
    setLayerPanelOpen(false);
    expect(isLayerPanelOpen()).toBe(false);

    let ticks = 0;
    const unsub = subscribeLayerPanel(() => {
      ticks += 1;
    });

    setLayerPanelOpen(true);
    expect(isLayerPanelOpen()).toBe(true);
    expect(ticks).toBe(1);

    setLayerPanelOpen(true);
    expect(ticks).toBe(1);

    setLayerPanelOpen(false);
    expect(isLayerPanelOpen()).toBe(false);
    expect(ticks).toBe(2);
    unsub();
  });
});
