import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ModeChips } from "./ModeChips";

describe("ModeChips", () => {
  it("offers automatic routing alongside all manual modes", () => {
    const onModeChange = vi.fn();
    render(
      <ModeChips
        mode="auto"
        capabilities={null}
        onModeChange={onModeChange}
      />,
    );

    expect(screen.getByRole("button", { name: "自动" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "生图" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "局部重绘" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "指令改图" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "元素拆解" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "文字编辑" })).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "局部重绘" }));
    expect(onModeChange).toHaveBeenCalledWith("inpaint");
  });
});
