/**
 * Bake layer bitmaps so tldraw's CSS `object-fit: cover` cannot crop FG/BG
 * differently from each other or from the source shape.
 */

export interface BakedLayerImage {
  src: string;
  w: number;
  h: number;
}

export interface CoverCropRect {
  sx: number;
  sy: number;
  sw: number;
  sh: number;
}

/**
 * Source rectangle for CSS ``object-fit: cover`` into ``destW×destH``.
 */
export function coverCropRect(
  srcW: number,
  srcH: number,
  destW: number,
  destH: number,
): CoverCropRect {
  if (srcW <= 0 || srcH <= 0 || destW <= 0 || destH <= 0) {
    return { sx: 0, sy: 0, sw: Math.max(0, srcW), sh: Math.max(0, srcH) };
  }
  const scale = Math.max(destW / srcW, destH / srcH);
  const sw = destW / scale;
  const sh = destH / scale;
  return {
    sx: (srcW - sw) / 2,
    sy: (srcH - sh) / 2,
    sw,
    sh,
  };
}

function loadHtmlImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("failed to load layer image"));
    image.src = src;
  });
}

/**
 * Draw ``img`` into ``destW×destH`` with the same centering crop as CSS
 * ``object-fit: cover`` (scale to fill, crop overflow, centered).
 */
export function drawImageCover(
  ctx: CanvasRenderingContext2D,
  img: CanvasImageSource & { width: number; height: number },
  destW: number,
  destH: number,
): void {
  const { sx, sy, sw, sh } = coverCropRect(img.width, img.height, destW, destH);
  if (sw <= 0 || sh <= 0) return;
  ctx.drawImage(img, sx, sy, sw, sh, 0, 0, destW, destH);
}

/**
 * Rasterize a layer URL into an exact ``boxW×boxH`` PNG data URL.
 * Natural aspect then matches the shape box, so tldraw cover is a no-op crop.
 */
export async function bakeLayerToShapeBox(
  src: string,
  boxW: number,
  boxH: number,
): Promise<BakedLayerImage> {
  const w = Math.max(1, Math.round(boxW));
  const h = Math.max(1, Math.round(boxH));
  const image = await loadHtmlImage(src);
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("canvas 2d unavailable");
  drawImageCover(ctx, image, w, h);
  return { src: canvas.toDataURL("image/png"), w, h };
}
