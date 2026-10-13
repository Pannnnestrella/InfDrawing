import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MaskTool } from "./MaskTool";

describe("MaskTool", () => {
  it("renders brush controls for a floating window and cancels", () => {
    const onCancel = vi.fn();
    render(<MaskTool imageUrl="" onComplete={vi.fn()} onCancel={onCancel} />);

    expect(screen.getByText(/拖动标题栏移动窗口/)).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
