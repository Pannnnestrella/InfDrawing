export type MaskPoint = { x: number; y: number };

/** Convert pointer coordinates within a source-aspect canvas to source pixels. */
export function maskPoint(
  clientX: number, clientY: number,
  rect: { left: number; top: number; width: number; height: number },
  width: number, height: number,
): MaskPoint {
  return {
    x: Math.max(0, Math.min(width - 1, (clientX - rect.left) / rect.width * width)),
    y: Math.max(0, Math.min(height - 1, (clientY - rect.top) / rect.height * height)),
  };
}

/** Reject degenerate lasso selections before rasterization. */
export function polygonArea(points: MaskPoint[]): number {
  return Math.abs(points.reduce((sum, point, index) => {
    const next = points[(index + 1) % points.length];
    return sum + point.x * next.y - next.x * point.y;
  }, 0)) / 2;
}
