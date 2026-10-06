import type { BBox } from "@/lib/controlled-edit-api";

export type BBoxHandle = "move" | "nw" | "ne" | "sw" | "se";

/** Smallest editable side, as a fraction of the image. */
export const MIN_BBOX_SIDE = 0.02;

/** Box offered when an entity has no box yet. */
export const DEFAULT_BBOX: BBox = { x: 0.35, y: 0.35, w: 0.3, h: 0.3 };

const clamp = (value: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, value));

/**
 * Apply a pointer drag (in normalized image units) to a box.
 *
 * "move" translates the box inside the image; corner handles move one corner while the
 * opposite corner stays fixed, never shrinking below MIN_BBOX_SIDE.
 */
export function applyBBoxDrag(start: BBox, handle: BBoxHandle, dx: number, dy: number): BBox {
  if (handle === "move") {
    return {
      x: clamp(start.x + dx, 0, 1 - start.w),
      y: clamp(start.y + dy, 0, 1 - start.h),
      w: start.w,
      h: start.h,
    };
  }
  let x0 = start.x;
  let y0 = start.y;
  let x1 = start.x + start.w;
  let y1 = start.y + start.h;
  if (handle === "nw" || handle === "sw") x0 = clamp(x0 + dx, 0, x1 - MIN_BBOX_SIDE);
  if (handle === "ne" || handle === "se") x1 = clamp(x1 + dx, x0 + MIN_BBOX_SIDE, 1);
  if (handle === "nw" || handle === "ne") y0 = clamp(y0 + dy, 0, y1 - MIN_BBOX_SIDE);
  if (handle === "sw" || handle === "se") y1 = clamp(y1 + dy, y0 + MIN_BBOX_SIDE, 1);
  return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
}

/** Round to 4 decimals so saved boxes stay readable and stable. */
export function roundBBox(box: BBox): BBox {
  const r = (v: number) => Math.round(v * 10_000) / 10_000;
  return { x: r(box.x), y: r(box.y), w: r(box.w), h: r(box.h) };
}
