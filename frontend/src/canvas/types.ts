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

/** Image currently targeted by the chat composer. */
export interface SelectedImageChip {
  id: string;
  name: string;
  thumbSrc: string | null;
}
