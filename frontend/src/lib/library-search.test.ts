import { describe, expect, it } from "vitest";

import type { AssetItem } from "./library-api";
import { itemMatchesQuery } from "./library-search";

function item(overrides: Partial<AssetItem> = {}): AssetItem {
  return {
    id: "1",
    owner_key_id: "k",
    library_id: "lib",
    artifact_id: "art",
    title: "红披风骑士",
    objects: ["骑士", "长剑"],
    tags: ["奇幻"],
    keywords: [],
    description: "夜景城堡前的骑士。",
    source_project: "",
    character_name: "",
    content_sha256: "",
    style: "电影光，冷色调",
    asset_type: "character",
    view: "full_body",
    genre: "fantasy",
    background: "environment",
    pose: "standing",
    palette: ["红", "金"],
    materials: ["金属"],
    caption_status: "ok",
    caption_error: null,
    shape_feat: null,
    created_at: "",
    updated_at: "",
    ...overrides,
  };
}

describe("itemMatchesQuery", () => {
  it("matches description and style", () => {
    expect(itemMatchesQuery(item(), "夜景")).toBe(true);
    expect(itemMatchesQuery(item(), "冷色")).toBe(true);
    expect(itemMatchesQuery(item(), "角色")).toBe(true);
    expect(itemMatchesQuery(item(), "赛博")).toBe(false);
  });

  it("treats empty query as match-all", () => {
    expect(itemMatchesQuery(item(), "  ")).toBe(true);
  });

  it("matches keywords, source project, and character name", () => {
    const row = item({
      keywords: ["持剑"],
      source_project: "骑士demo",
      character_name: "女剑士",
    });
    expect(itemMatchesQuery(row, "持剑")).toBe(true);
    expect(itemMatchesQuery(row, "骑士demo")).toBe(true);
    expect(itemMatchesQuery(row, "女剑士")).toBe(true);
  });
});
