"use client";

import {
  DefaultContextMenu,
  DefaultContextMenuContent,
  TldrawUiMenuGroup,
  TldrawUiMenuItem,
  type TLUiContextMenuProps,
} from "@tldraw/tldraw";

import { getCanvasEditor, getSelectedImageShapes } from "@/lib/canvas-bridge";
import { openCanvasRequest } from "@/lib/canvas-request-store";

function resolveGenerateAnchor(): { pageX: number; pageY: number } | null {
  const editor = getCanvasEditor();
  if (!editor) return null;

  const selectionBounds = editor.getSelectionPageBounds();
  if (selectionBounds) {
    return { pageX: selectionBounds.x, pageY: selectionBounds.y };
  }

  const center = editor.getViewportPageBounds().center;
  return { pageX: center.x - 256, pageY: center.y - 256 };
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
