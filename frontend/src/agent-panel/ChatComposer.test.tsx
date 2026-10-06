import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ChatComposer } from "./ChatComposer";

const baseProps = {
  message: "",
  mode: "auto" as const,
  capabilities: null,
  enginePreference: { mode: "auto" as const, cloudProvider: "openai" as const },
  busy: false,
  modeEnabled: true,
  modeDisabledReason: null,
  selectionHint: null,
  canvasReady: true,
  canvasHasSelection: false,
  canvasHasMask: false,
  textRegions: [],
  selectedTextIndex: null,
  ocrLoading: false,
  ocrError: null,
  onMessageChange: vi.fn(),
  onModeChange: vi.fn(),
  onEngineChange: vi.fn(),
  onSubmit: vi.fn(),
  onOpenMaskEditor: vi.fn(),
  onSelectTextRegion: vi.fn(),
  onRetryOcr: vi.fn(),
};

describe("ChatComposer", () => {
  it("opens studio from the dedicated entry", () => {
    const onOpenStudio = vi.fn();
    render(<ChatComposer {...baseProps} onOpenStudio={onOpenStudio} />);
    fireEvent.click(screen.getByRole("button", { name: "多轮编辑" }));
    expect(onOpenStudio).toHaveBeenCalledTimes(1);
  });

  it("opens the library panel from the dedicated entry", () => {
    const onOpenLibrary = vi.fn();
    render(<ChatComposer {...baseProps} onOpenLibrary={onOpenLibrary} />);
    fireEvent.click(screen.getByRole("button", { name: "素材库" }));
    expect(onOpenLibrary).toHaveBeenCalledTimes(1);
  });
});
