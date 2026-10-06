import { describe, expect, it } from "vitest";

import type { EditVersion } from "@/lib/controlled-edit-api";

import { ancestryPath, layoutVersionTree } from "./version-tree-layout";

function version(id: string, parentId: string | null, minute: number): EditVersion {
  return {
    id,
    session_id: "s",
    parent_id: parentId,
    status: "succeeded",
    progress_step: null,
    image_artifact_id: `a-${id}`,
    width: 100,
    height: 100,
    instruction: null,
    intent: null,
    compiled_prompt: null,
    reference_artifact_ids: [],
    entities: [],
    verification: null,
    attempts: 0,
    warnings: [],
    error: null,
    prompt_style: null,
    image_provider: null,
    created_at: `2026-10-05T10:${String(minute).padStart(2, "0")}:00Z`,
    updated_at: `2026-10-05T10:${String(minute).padStart(2, "0")}:00Z`,
  };
}

describe("layoutVersionTree", () => {
  // root ─ a ─ c
  //    └── b
  const versions = [
    version("c", "a", 3),
    version("root", null, 0),
    version("b", "root", 2),
    version("a", "root", 1),
  ];

  it("keeps the first child on the parent lane and branches later siblings", () => {
    const layout = layoutVersionTree(versions);
    const byId = Object.fromEntries(layout.nodes.map((n) => [n.version.id, n]));

    expect(byId.root).toMatchObject({ depth: 0, lane: 0, ordinal: 1 });
    expect(byId.a).toMatchObject({ depth: 1, lane: 0, ordinal: 2 });
    expect(byId.c).toMatchObject({ depth: 2, lane: 0, ordinal: 4 });
    expect(byId.b).toMatchObject({ depth: 1, lane: 1, ordinal: 3 });
    expect(layout.depthCount).toBe(3);
    expect(layout.laneCount).toBe(2);
    expect(layout.edges.map((e) => `${e.from.version.id}>${e.to.version.id}`).sort()).toEqual([
      "a>c",
      "root>a",
      "root>b",
    ]);
  });

  it("handles an empty tree", () => {
    expect(layoutVersionTree([])).toMatchObject({ nodes: [], depthCount: 0, laneCount: 0 });
  });

  it("returns the ancestry path from root to the current node", () => {
    expect(ancestryPath(versions, "c")).toEqual(["root", "a", "c"]);
    expect(ancestryPath(versions, null)).toEqual([]);
  });
});
