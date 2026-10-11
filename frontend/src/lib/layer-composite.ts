/**
 * Geometry and pixel helpers for merging image layers on the client.
 * Keeps merge math testable without a live tldraw Editor.
 */

export interface LayerRect {
  x: number;
  y: number;
  w: number;
  h: number;
  hidden?: boolean;
}

export interface CompositeBounds {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface CompositeDrawLayer {
  x: number;
  y: number;
  w: number;
  h: number;
  opacity: number;
  hidden: boolean;
  /** Decoded bitmap / HTMLImageElement ready for canvas drawImage. */
  source: CanvasImageSource;
}

/** Axis-aligned union of non-hidden layer rects, or null when none contribute. */
export function computeCompositeBounds(layers: LayerRect[]): CompositeBounds | null {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  let any = false;
  for (const layer of layers) {
    if (layer.hidden) continue;
    if (!(layer.w > 0 && layer.h > 0)) continue;
    any = true;
    minX = Math.min(minX, layer.x);
    minY = Math.min(minY, layer.y);
    maxX = Math.max(maxX, layer.x + layer.w);
    maxY = Math.max(maxY, layer.y + layer.h);
  }
  if (!any) return null;
  return {
    x: minX,
    y: minY,
    w: Math.max(1, Math.ceil(maxX - minX)),
    h: Math.max(1, Math.ceil(maxY - minY)),
  };
}

/**
 * Draw layers bottom→top into a transparent canvas and return a PNG data URL.
 * Hidden layers are skipped; opacity is applied via globalAlpha.
 */
export function compositeLayersToDataUrl(layers: CompositeDrawLayer[]): string | null {
  const bounds = computeCompositeBounds(layers);
  if (!bounds) return null;

  const canvas = document.createElement("canvas");
  canvas.width = bounds.w;
  canvas.height = bounds.h;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;

  ctx.clearRect(0, 0, bounds.w, bounds.h);
  for (const layer of layers) {
    if (layer.hidden) continue;
    ctx.save();
    ctx.globalAlpha = Math.min(1, Math.max(0, layer.opacity));
    ctx.drawImage(
      layer.source,
      layer.x - bounds.x,
      layer.y - bounds.y,
      layer.w,
      layer.h,
    );
    ctx.restore();
  }
  return canvas.toDataURL("image/png");
}

/** Transparent PNG data URL of the given size (for new blank layers). */
export function createTransparentPngDataUrl(width: number, height: number): string {
  const w = Math.max(1, Math.round(width));
  const h = Math.max(1, Math.round(height));
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  return canvas.toDataURL("image/png");
}

export function nextBlankLayerName(existingNames: string[]): string {
  const used = new Set(existingNames);
  let n = 1;
  while (used.has(`图层 ${n}`)) n += 1;
  return `图层 ${n}`;
}

export function duplicateLayerName(sourceName: string): string {
  const base = sourceName.trim() || "图层";
  if (base.endsWith(" 副本")) return `${base} 2`;
  const match = /^(.*) 副本(?: (\d+))?$/.exec(base);
  if (match) {
    const stem = match[1] ?? base;
    const num = match[2] ? Number(match[2]) + 1 : 2;
    return `${stem} 副本 ${num}`;
  }
  return `${base} 副本`;
}
