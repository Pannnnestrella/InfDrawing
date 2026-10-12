import {
  AssetRecordType,
  createShapeId,
  toRichText,
  type Editor,
  type TLAssetId,
  type TLImageShape,
  type TLShapeId,
} from "@tldraw/tldraw";

import {
  INPAINT_CANVAS_SIZE,
  type CanvasContextSnapshot,
  type CanvasMaskPair,
  type SelectedImageChip,
} from "@/canvas/types";
import {
  compositeLayersToDataUrl,
  computeCompositeBounds,
  createTransparentPngDataUrl,
  duplicateLayerName,
  nextBlankLayerName,
} from "@/lib/layer-composite";
import { bakeLayerToShapeBox } from "@/lib/layer-paste-bake";
import { resolveLayerPasteFrame } from "@/lib/layer-paste-frame";
import {
  mergeLayerMeta,
  readLayerMeta,
  resolveLayerName,
  sortByIndexBottomFirst,
  sortByIndexTopFirst,
  type CanvasLayerInfo,
  type LayerReorderDirection,
} from "@/lib/layer-model";
import { toTldrawCompatibleSrc } from "@/lib/tldraw-asset-src";

export type { CanvasLayerInfo, LayerReorderDirection } from "@/lib/layer-model";
export type { SelectedImageChip } from "@/canvas/types";

const PASTE_OFFSET_PX = 24;
const DEFAULT_BLANK_SIZE = 512;

interface LayerClipboardEntry {
  dataUrl: string;
  w: number;
  h: number;
  name: string;
  opacity: number;
  /** Page position of the source when copied (paste offsets from here). */
  pageX: number;
  pageY: number;
}

let layerClipboard: LayerClipboardEntry | null = null;

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
  // Include session scope so selection changes notify subscribers immediately
  // (document-only listen misses getSelectedShapeIds updates).
  storeUnlisten = editor.store.listen(
    () => {
      notify();
    },
    { scope: "all", source: "all" },
  );
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
  // Align with getSelectedImageShape(): multi-image select uses the topmost image.
  if (getSelectedImageShape()) return null;
  const selectedIds = editor.getSelectedShapeIds();
  if (selectedIds.length === 0) return "请在画布上选中一张图片";
  return "当前选中的不是图片图层";
}

/** Display name and thumbnail for the image the chat composer should show. */
export function getSelectedImageChip(): SelectedImageChip | null {
  const shape = getSelectedImageShape();
  if (!shape) return null;
  const layer = listImageLayers().find((item) => item.id === shape.id);
  if (!layer) return null;
  return { id: layer.id, name: layer.name, thumbSrc: layer.thumbSrc };
}

/** Fetchable preview URL, including tldraw `asset:` sources. */
export async function resolveSelectedImageThumb(shapeId: string): Promise<string | null> {
  const shape = getImageShapeById(shapeId);
  if (!shape || !editor) return null;
  const direct = imageThumbSrc(shape);
  if (direct) return direct;
  const assetId = shape.props.assetId;
  if (!assetId) return null;
  const asset = editor.getAsset(assetId);
  const src = asset?.props.src;
  if (!src || typeof src !== "string") return null;
  try {
    return await resolveAssetSrc(src, assetId);
  } catch {
    return null;
  }
}

function imageThumbSrc(shape: TLImageShape): string | null {
  if (!editor) return null;
  const assetId = shape.props.assetId;
  if (!assetId) return null;
  const asset = editor.getAsset(assetId);
  const src = asset?.props.src;
  if (!src || typeof src !== "string") return null;
  if (isDirectFetchableUrl(src)) return src;
  return null;
}

function imageAssetName(shape: TLImageShape): string | null {
  if (!editor) return null;
  const assetId = shape.props.assetId;
  if (!assetId) return null;
  const asset = editor.getAsset(assetId);
  if (!asset || asset.type !== "image") return null;
  const name = asset.props.name;
  return typeof name === "string" && name ? name : null;
}

function getImageShapeById(id: string): TLImageShape | null {
  if (!editor) return null;
  const shape = editor.getShape(id as TLShapeId);
  if (!shape || shape.type !== "image") return null;
  return shape as TLImageShape;
}

/**
 * Current-page image layers, top-first (Photoshop-style).
 * Non-image shapes are ignored so the panel stays aligned with gen/decompose/ingest.
 */
export function listImageLayers(): CanvasLayerInfo[] {
  if (!editor) return [];
  const selected = new Set(editor.getSelectedShapeIds());
  const images = editor
    .getCurrentPageShapes()
    .filter((s): s is TLImageShape => s.type === "image");
  const ordered = sortByIndexTopFirst(images);
  const total = ordered.length;
  return ordered.map((shape, topFirstIndex) => {
    const meta = readLayerMeta(shape.meta as Record<string, unknown>);
    const assetName = imageAssetName(shape);
    return {
      id: shape.id,
      name: resolveLayerName(meta, assetName, total - topFirstIndex),
      index: shape.index,
      hidden: meta.hidden === true,
      locked: shape.isLocked,
      opacity: shape.opacity,
      selected: selected.has(shape.id),
      thumbSrc: imageThumbSrc(shape),
      assetName,
      meta,
    };
  });
}

export function selectLayer(id: string, opts?: { additive?: boolean }): boolean {
  const shape = getImageShapeById(id);
  if (!editor || !shape) return false;
  if (opts?.additive) {
    const current = [...editor.getSelectedShapeIds()];
    if (current.includes(shape.id)) {
      editor.setSelectedShapes(current.filter((sid) => sid !== shape.id));
    } else {
      editor.setSelectedShapes([...current, shape.id]);
    }
  } else {
    editor.select(shape.id);
  }
  return true;
}

export function hasLayerClipboard(): boolean {
  return layerClipboard !== null;
}

export function setLayerHidden(id: string, hidden: boolean): boolean {
  const shape = getImageShapeById(id);
  if (!editor || !shape) return false;
  const meta = mergeLayerMeta(shape.meta as Record<string, unknown>, { hidden });
  // Allow hide/show even when the shape is locked (lock means transform-lock).
  editor.run(
    () => {
      editor!.updateShape({ id: shape.id, type: "image", meta });
    },
    { ignoreShapeLock: true },
  );
  return true;
}

export function setLayerLocked(id: string, locked: boolean): boolean {
  const shape = getImageShapeById(id);
  if (!editor || !shape) return false;
  if (shape.isLocked === locked) return true;
  editor.toggleLock([shape.id]);
  return true;
}

export function renameLayer(id: string, name: string): boolean {
  const shape = getImageShapeById(id);
  if (!editor || !shape) return false;
  const trimmed = name.trim();
  if (!trimmed) return false;
  const meta = mergeLayerMeta(shape.meta as Record<string, unknown>, {
    layerName: trimmed,
  });
  editor.run(
    () => {
      editor!.updateShape({ id: shape.id, type: "image", meta });
    },
    { ignoreShapeLock: true },
  );
  return true;
}

export function reorderLayer(id: string, direction: LayerReorderDirection): boolean {
  const shape = getImageShapeById(id);
  if (!editor || !shape) return false;
  switch (direction) {
    case "up":
      editor.bringForward([shape.id]);
      break;
    case "down":
      editor.sendBackward([shape.id]);
      break;
    case "front":
      editor.bringToFront([shape.id]);
      break;
    case "back":
      editor.sendToBack([shape.id]);
      break;
    default:
      return false;
  }
  return true;
}

async function resolveShapeDataUrl(shape: TLImageShape): Promise<string | null> {
  if (!editor) return null;
  const assetId = shape.props.assetId;
  if (!assetId) return null;
  const asset = editor.getAsset(assetId);
  const src = asset?.props.src;
  if (!src || typeof src !== "string") return null;
  if (src.startsWith("data:")) return src;
  try {
    const file = await fetchAssetAsFile(src, "layer.png", assetId);
    const buffer = await file.arrayBuffer();
    const bytes = new Uint8Array(buffer);
    let binary = "";
    for (let i = 0; i < bytes.length; i += 1) {
      binary += String.fromCharCode(bytes[i] ?? 0);
    }
    return `data:image/png;base64,${btoa(binary)}`;
  } catch {
    return null;
  }
}

function loadHtmlImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("failed to decode layer image"));
    img.src = src;
  });
}

async function createImageLayerAt(opts: {
  dataUrl: string;
  pageX: number;
  pageY: number;
  w: number;
  h: number;
  name: string;
  opacity?: number;
}): Promise<TLShapeId | null> {
  if (!editor) return null;
  const assetSrc = await toTldrawCompatibleSrc(opts.dataUrl);
  const assetId = AssetRecordType.createId();
  const shapeId = createShapeId();
  editor.createAssets([
    {
      id: assetId,
      type: "image",
      typeName: "asset",
      props: {
        name: `${opts.name}.png`,
        src: assetSrc,
        w: opts.w,
        h: opts.h,
        mimeType: "image/png",
        isAnimated: false,
      },
      meta: {},
    },
  ]);
  editor.createShape({
    id: shapeId,
    type: "image",
    x: opts.pageX,
    y: opts.pageY,
    opacity: opts.opacity ?? 1,
    props: {
      assetId,
      w: opts.w,
      h: opts.h,
    },
    meta: mergeLayerMeta({}, { layerName: opts.name }),
  });
  return shapeId;
}

/** Create a transparent image layer (size from selection or 512²). */
export async function createBlankLayer(): Promise<boolean> {
  if (!editor) return false;
  const selected = getSelectedImageShape();
  const w = selected ? Math.round(selected.props.w) : DEFAULT_BLANK_SIZE;
  const h = selected ? Math.round(selected.props.h) : DEFAULT_BLANK_SIZE;
  const name = nextBlankLayerName(listImageLayers().map((layer) => layer.name));
  let pageX: number;
  let pageY: number;
  if (selected) {
    pageX = selected.x;
    pageY = selected.y;
  } else {
    const center = editor.screenToPage(editor.getViewportScreenCenter());
    pageX = center.x - w / 2;
    pageY = center.y - h / 2;
  }
  const dataUrl = createTransparentPngDataUrl(w, h);
  const shapeId = await createImageLayerAt({
    dataUrl,
    pageX,
    pageY,
    w,
    h,
    name,
  });
  if (!shapeId) return false;
  editor.select(shapeId);
  return true;
}

/** Copy the preferred selected image layer into the in-app clipboard. */
export async function copySelectedLayer(): Promise<boolean> {
  const shape = getSelectedImageShape();
  if (!editor || !shape) return false;
  const dataUrl = await resolveShapeDataUrl(shape);
  if (!dataUrl) return false;
  const meta = readLayerMeta(shape.meta as Record<string, unknown>);
  const name = resolveLayerName(meta, imageAssetName(shape), 1);
  layerClipboard = {
    dataUrl,
    w: Math.round(shape.props.w),
    h: Math.round(shape.props.h),
    name,
    opacity: shape.opacity,
    pageX: shape.x,
    pageY: shape.y,
  };
  notify();
  return true;
}

/** Paste the in-app clipboard as a new layer (offset 24px). */
export async function pasteLayerClipboard(): Promise<boolean> {
  if (!editor || !layerClipboard) return false;
  const name = duplicateLayerName(layerClipboard.name);
  const shapeId = await createImageLayerAt({
    dataUrl: layerClipboard.dataUrl,
    pageX: layerClipboard.pageX + PASTE_OFFSET_PX,
    pageY: layerClipboard.pageY + PASTE_OFFSET_PX,
    w: layerClipboard.w,
    h: layerClipboard.h,
    name,
    opacity: layerClipboard.opacity,
  });
  if (!shapeId) return false;
  // Next paste keeps stacking from the new position.
  layerClipboard = {
    ...layerClipboard,
    pageX: layerClipboard.pageX + PASTE_OFFSET_PX,
    pageY: layerClipboard.pageY + PASTE_OFFSET_PX,
    name,
  };
  editor.select(shapeId);
  notify();
  return true;
}

/** Copy then paste the current selection as an independent layer. */
export async function duplicateSelectedLayer(): Promise<boolean> {
  const ok = await copySelectedLayer();
  if (!ok) return false;
  return pasteLayerClipboard();
}

/**
 * Merge currently selected image layers (bottom→top), delete sources, keep result.
 * Requires at least two selected image shapes.
 */
export async function mergeSelectedLayers(): Promise<boolean> {
  if (!editor) return false;
  const selected = getSelectedImageShapes().filter((shape) => {
    const meta = readLayerMeta(shape.meta as Record<string, unknown>);
    return meta.hidden !== true;
  });
  if (selected.length < 2) return false;

  const bottomFirst = sortByIndexBottomFirst(selected);
  const drawLayers = [];
  for (const shape of bottomFirst) {
    const dataUrl = await resolveShapeDataUrl(shape);
    if (!dataUrl) return false;
    const source = await loadHtmlImage(dataUrl);
    drawLayers.push({
      x: shape.x,
      y: shape.y,
      w: Math.round(shape.props.w),
      h: Math.round(shape.props.h),
      opacity: shape.opacity,
      hidden: false,
      source,
    });
  }

  const dataUrl = compositeLayersToDataUrl(drawLayers);
  if (!dataUrl) return false;

  const box = computeCompositeBounds(drawLayers);
  if (!box) return false;

  const remainingNames = listImageLayers()
    .filter((layer) => !selected.some((shape) => shape.id === layer.id))
    .map((layer) => layer.name);
  let mergeName = "合并图层";
  if (remainingNames.includes(mergeName)) {
    let n = 2;
    while (remainingNames.includes(`${mergeName} ${n}`)) n += 1;
    mergeName = `${mergeName} ${n}`;
  }

  const shapeId = await createImageLayerAt({
    dataUrl,
    pageX: box.x,
    pageY: box.y,
    w: box.w,
    h: box.h,
    name: mergeName,
  });
  if (!shapeId) return false;

  const ids = bottomFirst.map((shape) => shape.id);
  editor.run(
    () => {
      editor!.deleteShapes(ids);
    },
    { ignoreShapeLock: true },
  );
  editor.select(shapeId);
  return true;
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
  // Fresh pastes may take a moment before asset.src is fetchable.
  for (let attempt = 0; attempt < 6; attempt += 1) {
    const shape = getSelectedImageShape();
    if (!shape) return null;
    try {
      const file = await exportImageShapeFile(shape);
      if (file) return file;
    } catch {
      // Retry below.
    }
    if (attempt < 5) {
      await new Promise((resolve) => setTimeout(resolve, 350));
    }
  }
  return null;
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

/**
 * Stack decompose layers at the source image frame (background first, foreground on top).
 *
 * tldraw renders images with CSS ``object-fit: cover``. If FG/BG natural aspects
 * differ from the shape box (or each other), cover crops them differently and they
 * look vertically/horizontally offset. Bake each layer into the exact shape box
 * first so cover becomes a no-op and layers stay registered to the source.
 */
export async function pasteLayersToCanvas(
  layers: CanvasLayerInput[],
  anchor: { pageX: number; pageY: number; w?: number; h?: number },
): Promise<boolean> {
  if (!editor || layers.length === 0) return false;

  const selected = getSelectedImageShape();
  const frame = resolveLayerPasteFrame(
    anchor,
    selected
      ? {
          pageX: selected.x,
          pageY: selected.y,
          w: Math.round(selected.props.w),
          h: Math.round(selected.props.h),
        }
      : null,
  );
  const shapeIds: ReturnType<typeof createShapeId>[] = [];

  // Bake at 2× display pixels (same aspect) so cover stays a no-op without
  // crushing source detail down to the on-canvas box size.
  const bakeW = Math.max(1, Math.round(frame.w * 2));
  const bakeH = Math.max(1, Math.round(frame.h * 2));

  for (const layer of layers) {
    const rawSrc = await toTldrawCompatibleSrc(layer.image_url);
    const baked = await bakeLayerToShapeBox(rawSrc, bakeW, bakeH);

    const assetId = AssetRecordType.createId();
    const shapeId = createShapeId();

    editor.createAssets([
      {
        id: assetId,
        type: "image",
        typeName: "asset",
        props: {
          name: `${layer.label}.png`,
          src: baked.src,
          // Match shape box exactly so object-fit:cover does not re-crop.
          w: baked.w,
          h: baked.h,
          mimeType: "image/png",
          isAnimated: false,
        },
        meta: {},
      },
    ]);

    editor.createShape({
      id: shapeId,
      type: "image",
      x: frame.pageX,
      y: frame.pageY,
      props: {
        assetId,
        w: frame.w,
        h: frame.h,
      },
      meta: mergeLayerMeta({}, { layerName: layer.label }),
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

/** Page position + display size of the selected image (for aligned layer paste). */
export function getSelectedImageAnchor(): {
  pageX: number;
  pageY: number;
  w: number;
  h: number;
} | null {
  const shape = getSelectedImageShape();
  if (!shape) return null;
  return {
    pageX: shape.x,
    pageY: shape.y,
    w: Math.round(shape.props.w),
    h: Math.round(shape.props.h),
  };
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
