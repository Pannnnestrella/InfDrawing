/** Helpers for aligning decompose layer paste to the source image frame. */

export interface LayerPasteFrame {
  pageX: number;
  pageY: number;
  w: number;
  h: number;
}

/**
 * Resolve the on-canvas box layers should fill.
 *
 * Prefer the frame captured at submit (position + size). Only adopt a live
 * selection position when its display size still matches the captured frame —
 * that means the same source was dragged, not a different image selected.
 */
export function resolveLayerPasteFrame(
  anchor: { pageX: number; pageY: number; w?: number; h?: number },
  live: { pageX: number; pageY: number; w: number; h: number } | null,
  fallbackSize = 512,
): LayerPasteFrame {
  const hasAnchorSize = anchor.w != null && anchor.h != null;
  if (hasAnchorSize) {
    const w = Math.max(1, Math.round(anchor.w as number));
    const h = Math.max(1, Math.round(anchor.h as number));
    if (live && live.w === w && live.h === h) {
      return { pageX: live.pageX, pageY: live.pageY, w, h };
    }
    return { pageX: anchor.pageX, pageY: anchor.pageY, w, h };
  }

  if (live) {
    return {
      pageX: live.pageX,
      pageY: live.pageY,
      w: Math.max(1, Math.round(live.w)),
      h: Math.max(1, Math.round(live.h)),
    };
  }

  return {
    pageX: anchor.pageX,
    pageY: anchor.pageY,
    w: fallbackSize,
    h: fallbackSize,
  };
}
