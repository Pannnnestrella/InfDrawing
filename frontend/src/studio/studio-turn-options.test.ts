import { afterEach, describe, expect, it, vi } from "vitest";

import {
  loadPromptStyle,
  saveImageProvider,
  savePromptStyle,
  subscribeCeditOptions,
} from "./studio-turn-options";

describe("studio-turn-options", () => {
  afterEach(() => {
    sessionStorage.clear();
  });

  it("persists prompt style and notifies subscribers", () => {
    const listener = vi.fn();
    const unsubscribe = subscribeCeditOptions(listener);
    savePromptStyle("target_only");
    expect(loadPromptStyle()).toBe("target_only");
    expect(listener).toHaveBeenCalledTimes(1);
    saveImageProvider("openai");
    expect(listener).toHaveBeenCalledTimes(2);
    unsubscribe();
    savePromptStyle("preserve");
    expect(listener).toHaveBeenCalledTimes(2);
  });
});
