import {
  ASSET_TYPES,
  BACKGROUNDS,
  catalogSearchBlob,
  GENRES,
  POSES,
  VIEWS,
} from "./library-catalog";
import type { AssetItem } from "./library-api";

const QUERY_CHUNK_SPLIT = /[\s,，。；;、/|]+/;

/**
 * Approximate the backend OR tokenizer without jieba (production search hits the API).
 * Keeps whitespace/punctuation chunks of length >= 2.
 */
export function tokenizeQuery(query: string): string[] {
  const text = query.trim();
  if (!text) return [];
  const tokens: string[] = [];
  const seen = new Set<string>();
  for (const chunk of text.split(QUERY_CHUNK_SPLIT)) {
    const token = chunk.trim().toLowerCase();
    if (token.length < 2 || seen.has(token)) continue;
    seen.add(token);
    tokens.push(token);
  }
  if (tokens.length === 0) {
    const folded = text.toLowerCase();
    if (folded) tokens.push(folded);
  }
  return tokens;
}

function searchBlob(item: AssetItem): string {
  return [
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
}

/** Case-insensitive OR of token substrings across caption and game-catalog fields. */
export function itemMatchesQuery(item: AssetItem, query: string): boolean {
  const tokens = tokenizeQuery(query);
  if (tokens.length === 0) return true;
  const haystack = searchBlob(item);
  return tokens.some((token) => haystack.includes(token));
}
