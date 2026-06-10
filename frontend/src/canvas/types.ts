/** Canvas ↔ Agent shared types. */

export const INPAINT_CANVAS_SIZE = 512;

export interface CanvasMaskPair {
  image: File;
  mask: File;
}

export interface CanvasContextSnapshot {
  selectedShapeId: string | null;
  hasMask: boolean;
  imageWidth?: number;
  imageHeight?: number;
}
