import { describe, expect, it } from "vitest";

import { isQuotaErrorMessage } from "./quota-error";

describe("isQuotaErrorMessage", () => {
  it("detects rewritten and raw quota failures", () => {
    expect(isQuotaErrorMessage("阿里云 DashScope 余额不足或欠费，请充值后重试")).toBe(true);
    expect(isQuotaErrorMessage("OpenAI Images error: insufficient_quota")).toBe(true);
    expect(isQuotaErrorMessage("DeepSeek 余额不足，请充值后重试")).toBe(true);
  });

  it("ignores ordinary failures", () => {
    expect(isQuotaErrorMessage("请先在画布上选中一张图片")).toBe(false);
    expect(isQuotaErrorMessage("Qwen edit error (400): InvalidParameter")).toBe(false);
  });
});
