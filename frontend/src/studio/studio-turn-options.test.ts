import { afterEach, describe, expect, it, vi } from "vitest";

import {
  loadImageOption,
  loadPromptStyle,
  parseImageOptions,
  saveImageOption,
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
    const options = parseImageOptions(
      "dashscope|qwen-image-2.0;dashscope|qwen-image-2.1-pro;openai|gpt-image-1",
    );
    saveImageOption(options[1]);
    expect(loadImageOption(options)?.model).toBe("qwen-image-2.1-pro");
    expect(listener).toHaveBeenCalledTimes(2);
    unsubscribe();
    savePromptStyle("preserve");
    expect(listener).toHaveBeenCalledTimes(2);
  });

  it("lists qwen 3.0 / 2.x / wan 2.7 as distinct full-frame options", () => {
    const options = parseImageOptions(
      "dashscope|qwen-image-3.0-pro;dashscope|qwen-image-2.0;dashscope|qwen-image-2.1-pro;dashscope|wan2.7-image-pro",
    );
    expect(options.map((o) => o.model)).toEqual([
      "qwen-image-3.0-pro",
      "qwen-image-2.0",
      "qwen-image-2.1-pro",
      "wan2.7-image-pro",
    ]);
    expect(options[0].label).toContain("3.0");
    expect(options[3].label).toContain("万相 2.7");
  });
});
