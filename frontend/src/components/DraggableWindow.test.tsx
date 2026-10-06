import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DraggableWindow } from "./DraggableWindow";

describe("DraggableWindow", () => {
  it("calls onClose from the header button", () => {
    const onClose = vi.fn();
    render(
      <DraggableWindow title="多轮编辑" onClose={onClose}>
        <p>preview</p>
      </DraggableWindow>,
    );
    expect(screen.getByRole("dialog", { name: "多轮编辑" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "关闭" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
