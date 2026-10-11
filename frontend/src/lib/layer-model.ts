/**
 * Pure layer-domain helpers for InfDrawing canvas layers.
 *
 * Layers are tldraw image shapes; InfDrawing-specific fields live in `shape.meta`
 * so future features (opacity UI, blend modes, groups) can extend without a parallel store.
 */

export type LayerReorderDirection = "up" | "down" | "front" | "back";

/** InfDrawing-owned keys on `TLShape.meta`. Add optional fields here as features land. */
export interface LayerMeta {
  /** Display name in the layers panel. */
  layerName?: string;
  /** When true, shape is hidden via tldraw `getShapeVisibility`. */
  hidden?: boolean;
  /** Reserved: blend mode id (e.g. "multiply"). Not used in MVP. */
  blendMode?: string;
  /** Reserved: group membership for future layer folders. */
  groupId?: string;
}

/** Snapshot row for the layers panel (and future tooling). */
export interface CanvasLayerInfo {
  id: string;
  name: string;
  /** tldraw fractional index; higher sorts above in document order. */
  index: string;
  hidden: boolean;
  locked: boolean;
  /** Shape opacity 0–1; exposed for a future slider without another API pass. */
  opacity: number;
  selected: boolean;
  thumbSrc: string | null;
  assetName: string | null;
  meta: LayerMeta;
}

export function readLayerMeta(
  meta: Record<string, unknown> | null | undefined,
): LayerMeta {
  if (!meta) return {};
  const next: LayerMeta = {};
  if (typeof meta.layerName === "string" && meta.layerName.trim()) {
    next.layerName = meta.layerName.trim();
  }
  if (meta.hidden === true) next.hidden = true;
  if (typeof meta.blendMode === "string" && meta.blendMode) {
    next.blendMode = meta.blendMode;
  }
  if (typeof meta.groupId === "string" && meta.groupId) {
    next.groupId = meta.groupId;
  }
  return next;
}

/** JSON-compatible object for tldraw `shape.meta`. */
export type LayerMetaRecord = { [key: string]: string | number | boolean | null };

/** Merge a patch into existing shape meta without dropping unknown keys. */
export function mergeLayerMeta(
  existing: Record<string, unknown> | null | undefined,
  patch: Partial<LayerMeta>,
): LayerMetaRecord {
  const base: LayerMetaRecord = {};
  for (const [key, value] of Object.entries(existing ?? {})) {
    if (
      typeof value === "string" ||
      typeof value === "number" ||
      typeof value === "boolean" ||
      value === null
    ) {
      base[key] = value;
    }
  }
  if ("layerName" in patch) {
    const name = patch.layerName?.trim();
    if (name) base.layerName = name;
    else delete base.layerName;
  }
  // Always write a boolean: tldraw merges meta, so deleting the key cannot unhide.
  if ("hidden" in patch) {
    base.hidden = patch.hidden === true;
  }
  if ("blendMode" in patch) {
    if (patch.blendMode) base.blendMode = patch.blendMode;
    else delete base.blendMode;
  }
  if ("groupId" in patch) {
    if (patch.groupId) base.groupId = patch.groupId;
    else delete base.groupId;
  }
  return base;
}

export function resolveLayerName(
  meta: LayerMeta,
  assetName: string | null | undefined,
  fallbackIndex: number,
): string {
  if (meta.layerName) return meta.layerName;
  if (assetName) {
    const stripped = assetName.replace(/\.[a-z0-9]+$/i, "").trim();
    if (stripped) return stripped;
  }
  return `图层 ${fallbackIndex}`;
}

/** Sort by tldraw index ascending (bottom → top). */
export function sortByIndexBottomFirst<T extends { index: string }>(items: T[]): T[] {
  return [...items].sort((a, b) => {
    if (a.index < b.index) return -1;
    if (a.index > b.index) return 1;
    return 0;
  });
}

/** Top-first order for panel lists (Photoshop-style). */
export function sortByIndexTopFirst<T extends { index: string }>(items: T[]): T[] {
  return sortByIndexBottomFirst(items).reverse();
}

export function layerReorderAvailability(
  topFirstIndex: number,
  total: number,
): Record<LayerReorderDirection, boolean> {
  if (total <= 1) {
    return { up: false, down: false, front: false, back: false };
  }
  const notTop = topFirstIndex > 0;
  const notBottom = topFirstIndex < total - 1;
  return {
    up: notTop,
    front: notTop,
    down: notBottom,
    back: notBottom,
  };
}

/** tldraw visibility callback: hide when `meta.hidden` is set. */
export function shapeVisibilityFromMeta(
  meta: Record<string, unknown> | null | undefined,
): "hidden" | "inherit" {
  return meta?.hidden === true ? "hidden" : "inherit";
}
