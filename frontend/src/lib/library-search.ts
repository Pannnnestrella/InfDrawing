import {
  ASSET_TYPES,
  BACKGROUNDS,
  catalogSearchBlob,
  GENRES,
  POSES,
  VIEWS,
} from "./library-catalog";
import type { AssetItem } from "./library-api";

/** Case-insensitive substring match across caption and game-catalog fields. */
export function itemMatchesQuery(item: AssetItem, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  const haystack = [
    item.title,
    item.description,
    item.style,
    ...item.tags,
    ...(item.keywords ?? []),
    ...item.objects,
    item.source_project ?? "",
    item.character_name ?? "",
    ...(item.palette ?? []),
    ...(item.materials ?? []),
    catalogSearchBlob(ASSET_TYPES, item.asset_type ?? ""),
    catalogSearchBlob(VIEWS, item.view ?? ""),
    catalogSearchBlob(GENRES, item.genre ?? ""),
    catalogSearchBlob(BACKGROUNDS, item.background ?? ""),
    catalogSearchBlob(POSES, item.pose ?? ""),
  ]
    .join(" ")
    .toLowerCase();
  return haystack.includes(needle);
}
