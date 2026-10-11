"use client";

import {
  DefaultContextMenu,
  DefaultContextMenuContent,
  TldrawUiMenuGroup,
  TldrawUiMenuItem,
  type TLUiContextMenuProps,
} from "@tldraw/tldraw";

import {
  getCanvasEditor,
  getSelectedImageAnchor,
  getSelectedImageShapes,
} from "@/lib/canvas-bridge";
import {
  openCanvasRequest,
  type CanvasAnchor,
} from "@/lib/canvas-request-store";

function resolveGenerateAnchor(): CanvasAnchor | null {
  const frame = getSelectedImageAnchor();
  if (frame) return frame;

  const editor = getCanvasEditor();
  if (!editor) return null;

  const selectionBounds = editor.getSelectionPageBounds();
  if (selectionBounds) {
    return {
      pageX: selectionBounds.x,
      pageY: selectionBounds.y,
      w: Math.round(selectionBounds.w),
      h: Math.round(selectionBounds.h),
    };
  }

  const center = editor.getViewportPageBounds().center;
  return { pageX: center.x - 256, pageY: center.y - 256, w: 512, h: 512 };
}

export function AiContextMenu(props: TLUiContextMenuProps) {
  const hasSelectedImage = getSelectedImageShapes().length > 0;
  return (
    <DefaultContextMenu {...props}>
      <TldrawUiMenuGroup id="infdrawing-ai">
        <TldrawUiMenuItem
          id="infdrawing-ai-generate"
          label="AI 生图"
          icon="color"
          readonlyOk
          onSelect={() => {
            const anchor = resolveGenerateAnchor();
            if (anchor) openCanvasRequest("generate", anchor);
          }}
        />
        <TldrawUiMenuItem
          id="infdrawing-decompose"
          label="元素拆解"
          icon="layers"
          readonlyOk
          onSelect={() => {
            const anchor = resolveGenerateAnchor();
            if (anchor) openCanvasRequest("decompose", anchor);
          }}
        />
        {hasSelectedImage ? (
          <TldrawUiMenuItem
            id="infdrawing-library-ingest"
            label="加入素材库"
            icon="image"
            readonlyOk
            onSelect={() => {
              const anchor = resolveGenerateAnchor();
              if (anchor) openCanvasRequest("library-ingest", anchor);
            }}
          />
        ) : null}
      </TldrawUiMenuGroup>
      <DefaultContextMenuContent />
    </DefaultContextMenu>
  );
}
