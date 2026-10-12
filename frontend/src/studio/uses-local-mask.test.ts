import { describe, expect, it } from "vitest";

import type { SceneEntity } from "@/lib/controlled-edit-api";

import { usesLocalMask } from "./uses-local-mask";

function entity(
  id: string,
  bbox: { x: number; y: number; w: number; h: number } | null,
): SceneEntity {
  return {
    id,
    name: id,
    parent_id: null,
    description: "",
    status: "editable",
    bbox,
    bbox_source: "model",
    anchor_artifact_id: null,
    anchor_version_id: null,
  };
}

describe("usesLocalMask", () => {
  it("routes small character parts to local mask", () => {
    expect(
      usesLocalMask([entity("character.sword", { x: 0.1, y: 0.1, w: 0.1, h: 0.2 })]),
    ).toBe(true);
  });

  it("keeps background and whole subject on full-frame edit", () => {
    expect(
      usesLocalMask([entity("environment.sky", { x: 0, y: 0, w: 1, h: 0.4 })]),
    ).toBe(false);
    expect(usesLocalMask([entity("character", { x: 0.2, y: 0.1, w: 0.5, h: 0.8 })])).toBe(
      false,
    );
  });

  it("rejects missing or oversized boxes", () => {
    expect(usesLocalMask([entity("character.armor", null)])).toBe(false);
    expect(
      usesLocalMask([entity("character.skirt", { x: 0, y: 0.4, w: 0.6, h: 0.5 })]),
    ).toBe(false);
  });
});
