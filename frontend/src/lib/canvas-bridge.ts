import {
  AssetRecordType,
  createShapeId,
  toRichText,
  type Editor,
  type TLAssetId,
  type TLImageShape,
} from "@tldraw/tldraw";

import {
  INPAINT_CANVAS_SIZE,
  type CanvasContextSnapshot,
  type CanvasMaskPair,
} from "@/canvas/types";
import { toTldrawCompatibleSrc } from "@/lib/tldraw-asset-src";

type BridgeListener = () => void;

let editor: Editor | null = null;
let maskPair: CanvasMaskPair | null = null;
let storeUnlisten: (() => void) | null = null;
const listeners = new Set<BridgeListener>();

function notify() {
  listeners.forEach((fn) => fn());
}

function detachEditorListeners(): void {
  storeUnlisten?.();
  storeUnlisten = null;
}

export function subscribeCanvasBridge(listener: BridgeListener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function registerCanvasEditor(next: Editor): void {
  detachEditorListeners();
  editor = next;
  storeUnlisten = editor.store.listen(() => {
    notify();
  });
  notify();
}

export function unregisterCanvasEditor(): void {
  detachEditorListeners();
  editor = null;
  notify();
}

export function getCanvasEditor(): Editor | null {
  return editor;
}

export function setCanvasMaskPair(pair: CanvasMaskPair | null): void {
  maskPair = pair;
  notify();
}

export function getCanvasMaskPair(): CanvasMaskPair | null {
  return maskPair;
}

/** Image shapes in the current selection, in selection order. */
export function getSelectedImageShapes(): TLImageShape[] {
  if (!editor) return [];
  const shapes: TLImageShape[] = [];
  for (const id of editor.getSelectedShapeIds()) {
    const shape = editor.getShape(id);
    if (shape?.type === "image") shapes.push(shape as TLImageShape);
  }
  return shapes;
}

/**
 * Prefer a single selected image. After decompose both layers may stay selected;
 * fall back to the topmost by z-index so library ingest targets the foreground.
 */
export function getSelectedImageShape(): TLImageShape | null {
  const images = getSelectedImageShapes();
  if (images.length === 0) return null;
  if (images.length === 1) return images[0] ?? null;
  return (
    [...images].sort((a, b) => (a.index < b.index ? -1 : a.index > b.index ? 1 : 0)).at(-1) ??
    null
  );
}

export function getCanvasContextSnapshot(): CanvasContextSnapshot {
  const shape = getSelectedImageShape();
  return {
    selectedShapeId: shape?.id ?? null,
    hasMask: maskPair !== null,
    imageWidth: shape ? Math.round(shape.props.w) : undefined,
    imageHeight: shape ? Math.round(shape.props.h) : undefined,
  };
}

export function getCanvasSelectionHint(): string | null {
  if (!editor) return "画布加载中…";
  const selectedIds = editor.getSelectedShapeIds();
  if (selectedIds.length === 0) return "请在画布上选中一张图片";
  if (selectedIds.length > 1) return "请只选中一张图片（当前多选）";
  const shape = editor.getShape(selectedIds[0]);
  if (!shape) return "无法读取选中图层";
  if (shape.type !== "image") {
    return `当前选中的是「${shape.type}」，请选择图片图层`;
  }
  return null;
}

function isDirectFetchableUrl(src: string): boolean {
  return (
    src.startsWith("http://") ||
    src.startsWith("https://") ||
    src.startsWith("/") ||
    src.startsWith("data:") ||
    src.startsWith("blob:")
  );
}

/** Resolve tldraw asset: URLs to a fetchable http/blob/data URL. */
async function resolveAssetSrc(
  src: string,
  assetId: TLAssetId,
): Promise<string> {
  if (!editor) throw new Error("canvas editor not ready");
  if (isDirectFetchableUrl(src)) return src;
  const resolved = await editor.resolveAssetUrl(assetId, {
    shouldResolveToOriginal: true,
  });
  if (!resolved) {
    throw new Error("无法解析画布图片资源");
  }
  return resolved;
}

async function loadImageSize(url: string): Promise<{ w: number; h: number }> {
  return loadImageSizeWithRetry(url);
}

async function loadImageSizeWithRetry(
  url: string,
  attempts = 6,
  delayMs = 400,
): Promise<{ w: number; h: number }> {
  let lastError: Error | null = null;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      return await new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => resolve({ w: img.naturalWidth, h: img.naturalHeight });
        img.onerror = () => reject(new Error("failed to load image"));
        img.src = url;
      });
    } catch (err) {
      lastError = err instanceof Error ? err : new Error("failed to load image");
      if (attempt < attempts - 1) {
        await new Promise((resolve) => setTimeout(resolve, delayMs));
      }
    }
  }
  throw lastError ?? new Error("failed to load image");
}

async function fetchAssetAsFileWithRetry(
  src: string,
  name: string,
  assetId?: TLAssetId,
  attempts = 6,
  delayMs = 400,
): Promise<File> {
  let lastError: Error | null = null;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const fetchUrl =
        assetId && !isDirectFetchableUrl(src)
          ? await resolveAssetSrc(src, assetId)
          : src;
      const response = await fetch(fetchUrl);
      if (!response.ok) {
        throw new Error(`fetch asset failed: ${response.status}`);
      }
      const blob = await response.blob();
      return blobToFile(blob, name);
    } catch (err) {
      lastError = err instanceof Error ? err : new Error("fetch asset failed");
      if (attempt < attempts - 1) {
        await new Promise((resolve) => setTimeout(resolve, delayMs));
      }
    }
  }
  throw lastError ?? new Error("fetch asset failed");
}

async function blobToFile(blob: Blob, name: string): Promise<File> {
  return new File([blob], name, { type: blob.type || "image/png" });
}

/** Re-encode as PNG so multipart always declares a MIME the backend accepts. */
async function ensurePngFile(file: File, name = "canvas_image.png"): Promise<File> {
  if (file.type === "image/png" && file.size > 0) {
    return file.name === name ? file : new File([file], name, { type: "image/png" });
  }
  const bitmap = await createImageBitmap(file);
  try {
    const canvas = document.createElement("canvas");
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("canvas 2d unavailable");
    ctx.drawImage(bitmap, 0, 0);
    const blob = await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob(
        (b) => (b ? resolve(b) : reject(new Error("toBlob failed"))),
        "image/png",
      );
    });
    return new File([blob], name, { type: "image/png" });
  } finally {
    bitmap.close();
  }
}

async function resizeToSquarePng(file: File, size: number): Promise<File> {
  const bitmap = await createImageBitmap(file);
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("canvas 2d unavailable");
  ctx.drawImage(bitmap, 0, 0, size, size);
  bitmap.close();
  const blob = await new Promise<Blob>((resolve, reject) => {
    canvas.toBlob(
      (b) => (b ? resolve(b) : reject(new Error("toBlob failed"))),
      "image/png",
    );
  });
  return blobToFile(blob, `${file.name.replace(/\.\w+$/, "")}_512.png`);
}

async function fetchAssetAsFile(
  src: string,
  name: string,
  assetId?: TLAssetId,
): Promise<File> {
  return fetchAssetAsFileWithRetry(src, name, assetId);
}

/** Why the current selection cannot be exported for library ingest. */
export function getLibraryExportHint(): string | null {
  if (!editor) return "画布加载中…";
  const selectedIds = editor.getSelectedShapeIds();
  if (selectedIds.length === 0) return "请在画布上选中一张图片";
  const images = getSelectedImageShapes();
  if (images.length === 0) return "当前选中的不是图片图层";
  return null;
}

async function exportImageShapeFile(
  shape: TLImageShape,
  name = "canvas_image.png",
): Promise<File | null> {
  if (!editor) return null;
  const assetId = shape.props.assetId;
  if (!assetId) return null;
  const asset = editor.getAsset(assetId);
  const src = asset?.props.src;
  if (!src || typeof src !== "string") return null;
  const file = await fetchAssetAsFile(src, name, assetId);
  return ensurePngFile(file, name);
}

/** Export the selected image shape as original-resolution PNG. */
export async function exportSelectedImageFile(): Promise<File | null> {
  const shape = getSelectedImageShape();
  if (!shape) return null;
  return exportImageShapeFile(shape);
}

/** Export every selected image layer (background + foreground after decompose). */
export async function exportSelectedImageFiles(): Promise<File[]> {
  const files: File[] = [];
  for (const [index, shape] of getSelectedImageShapes().entries()) {
    const file = await exportImageShapeFile(shape, `canvas_image_${index + 1}.png`);
    if (file) files.push(file);
  }
  return files;
}

/** Export the selected image shape as 512×512 PNG for inpaint. */
export async function exportSelectedImageForInpaint(): Promise<File | null> {
  const shape = getSelectedImageShape();
  if (!shape || !editor) return null;
  const assetId = shape.props.assetId;
  if (!assetId) return null;
  const asset = editor.getAsset(assetId);
  const src = asset?.props.src;
  if (!src || typeof src !== "string") return null;
  const file = await fetchAssetAsFile(src, "canvas_image.png", assetId);
  return resizeToSquarePng(file, INPAINT_CANVAS_SIZE);
}

/** Resolve image + mask files for inpaint from canvas state. */
export async function resolveInpaintFilesFromCanvas(): Promise<CanvasMaskPair | null> {
  if (maskPair) return maskPair;
  return null;
}

/** Place a generated image at a page coordinate. */
export async function pasteImageUrlToCanvasAt(
  imageUrl: string,
  pageX: number,
  pageY: number,
): Promise<boolean> {
  if (!editor) return false;

  const assetSrc = await toTldrawCompatibleSrc(imageUrl);
  const { w, h } = await loadImageSize(assetSrc);
  const maxEdge = 512;
  const scale = Math.min(1, maxEdge / Math.max(w, h));
  const displayW = Math.round(w * scale);
  const displayH = Math.round(h * scale);

  const assetId = AssetRecordType.createId();
  const shapeId = createShapeId();

  editor.createAssets([
    {
      id: assetId,
      type: "image",
      typeName: "asset",
      props: {
        name: "generated.png",
        src: assetSrc,
        w: displayW,
        h: displayH,
        mimeType: "image/png",
        isAnimated: false,
      },
      meta: {},
    },
  ]);

  editor.createShape({
    id: shapeId,
    type: "image",
    x: pageX,
    y: pageY,
    props: {
      assetId,
      w: displayW,
      h: displayH,
    },
  });

  editor.select(shapeId);
  return true;
}

export interface CanvasLayerInput {
  label: string;
  image_url: string;
}

/** Stack decompose layers at the anchor (background first, foreground on top). */
export async function pasteLayersToCanvas(
  layers: CanvasLayerInput[],
  anchor: { pageX: number; pageY: number },
): Promise<boolean> {
  if (!editor || layers.length === 0) return false;

  const selected = getSelectedImageShape();
  const displayW = selected ? Math.round(selected.props.w) : 512;
  const displayH = selected ? Math.round(selected.props.h) : 512;
  const shapeIds: ReturnType<typeof createShapeId>[] = [];

  for (const layer of layers) {
    const assetSrc = await toTldrawCompatibleSrc(layer.image_url);
    const { w, h } = await loadImageSize(assetSrc);
    const scale = Math.min(displayW / w, displayH / h);
    const layerW = Math.round(w * scale);
    const layerH = Math.round(h * scale);

    const assetId = AssetRecordType.createId();
    const shapeId = createShapeId();

    editor.createAssets([
      {
        id: assetId,
        type: "image",
        typeName: "asset",
        props: {
          name: `${layer.label}.png`,
          src: assetSrc,
          w: layerW,
          h: layerH,
          mimeType: "image/png",
          isAnimated: false,
        },
        meta: {},
      },
    ]);

    editor.createShape({
      id: shapeId,
      type: "image",
      x: anchor.pageX,
      y: anchor.pageY,
      props: {
        assetId,
        w: layerW,
        h: layerH,
      },
    });

    shapeIds.push(shapeId);
  }

  // Select only the topmost (usually foreground) layer so follow-up actions
  // like「加入素材库」are not blocked by multi-select after decompose.
  const top = shapeIds[shapeIds.length - 1];
  if (top) editor.select(top);
  return true;
}

/** Place a generated image onto the canvas beside the current selection. */
export async function pasteImageUrlToCanvas(imageUrl: string): Promise<boolean> {
  if (!editor) return false;

  const selected = getSelectedImageShape();
  if (selected) {
    return pasteImageUrlToCanvasAt(
      imageUrl,
      selected.x + selected.props.w + 24,
      selected.y,
    );
  }

  const center = editor.getViewportPageBounds().center;
  return pasteImageUrlToCanvasAt(imageUrl, center.x - 256, center.y - 256);
}

export async function getSelectedImagePreviewUrl(): Promise<string | null> {
  const shape = getSelectedImageShape();
  if (!shape || !editor) return null;
  const assetId = shape.props.assetId;
  if (!assetId) return null;
  const asset = editor.getAsset(assetId);
  const src = asset?.props.src;
  if (!src || typeof src !== "string") return null;
  if (isDirectFetchableUrl(src)) return src;
  return editor.resolveAssetUrl(assetId, { shouldResolveToOriginal: true });
}

export function getSelectedImageAnchor(): { pageX: number; pageY: number } | null {
  const shape = getSelectedImageShape();
  if (!shape) return null;
  return { pageX: shape.x, pageY: shape.y };
}

/** Replace the selected image shape asset src in place. */
export async function replaceSelectedImageSrc(imageUrl: string): Promise<boolean> {
  const shape = getSelectedImageShape();
  if (!shape || !editor) return false;
  const assetId = shape.props.assetId;
  if (!assetId) return false;
  const asset = editor.getAsset(assetId);
  if (!asset || asset.type !== "image") return false;

  const assetSrc = await toTldrawCompatibleSrc(imageUrl);
  editor.updateAssets([
    {
      ...asset,
      props: {
        ...asset.props,
        src: assetSrc,
      },
    },
  ]);
  return true;
}

/** Overlay a text shape aligned to an image-space bbox on the selected image. */
export function overlayTextOnSelectedImage(
  newText: string,
  bbox: [number, number, number, number],
  imageSize: { width: number; height: number },
): boolean {
  if (!editor) return false;
  const shape = getSelectedImageShape();
  if (!shape) return false;

  const scaleX = shape.props.w / imageSize.width;
  const scaleY = shape.props.h / imageSize.height;
  const pageX = shape.x + bbox[0] * scaleX;
  const pageY = shape.y + bbox[1] * scaleY;
  const boxW = Math.max(24, (bbox[2] - bbox[0]) * scaleX);

  const textId = createShapeId();
  editor.createShape({
    id: textId,
    type: "text",
    x: pageX,
    y: pageY,
    props: {
      richText: toRichText(newText),
      w: boxW,
      autoSize: true,
      scale: Math.max(0.5, Math.min(2, scaleY)),
    },
  });
  editor.select(textId);
  return true;
}
