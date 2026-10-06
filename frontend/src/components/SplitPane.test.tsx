import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SplitPane } from "./SplitPane";

function mockContainerSize(separator: HTMLElement, width: number, height: number) {
  const pane = separator.parentElement;
  if (!pane) throw new Error("missing split container");
  vi.spyOn(pane, "getBoundingClientRect").mockReturnValue({
    width,
    height,
    top: 0,
    left: 0,
    bottom: height,
    right: width,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  });
}

describe("SplitPane", () => {
  it("resizes the trailing pane when the separator is dragged", () => {
    const onChange = vi.fn();
    render(
      <SplitPane
        axis="x"
        secondarySize={320}
        minSecondary={220}
        minPrimary={200}
        onSecondarySizeChange={onChange}
        label="调整右侧栏宽度"
      >
        <div>left</div>
        <div>right</div>
      </SplitPane>,
    );
    const separator = screen.getByRole("button", { name: "调整右侧栏宽度" });
    mockContainerSize(separator, 800, 400);
    fireEvent.pointerDown(separator, { clientX: 480, clientY: 20 });
    fireEvent.pointerMove(window, { clientX: 430, clientY: 20 });
    fireEvent.pointerUp(window);
    expect(onChange).toHaveBeenLastCalledWith(370);
  });

  it("does not shrink the trailing pane below minSecondary", () => {
    const onChange = vi.fn();
    render(
      <SplitPane
        axis="y"
        secondarySize={160}
        minSecondary={96}
        minPrimary={200}
        onSecondarySizeChange={onChange}
        label="调整修改树高度"
      >
        <div>top</div>
        <div>bottom</div>
      </SplitPane>,
    );
    const separator = screen.getByRole("button", { name: "调整修改树高度" });
    mockContainerSize(separator, 400, 600);
    fireEvent.pointerDown(separator, { clientX: 10, clientY: 440 });
    fireEvent.pointerMove(window, { clientX: 10, clientY: 580 });
    fireEvent.pointerUp(window);
    expect(onChange).toHaveBeenLastCalledWith(96);
  });
});
