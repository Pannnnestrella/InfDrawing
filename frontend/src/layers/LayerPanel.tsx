"use client";

import { useEffect, useState } from "react";

import {
  EyeIcon,
  EyeOffIcon,
  ImageIcon,
  LockIcon,
  UnlockIcon,
} from "@/components/icons";
import {
  copySelectedLayer,
  createBlankLayer,
  duplicateSelectedLayer,
  hasLayerClipboard,
  listImageLayers,
  mergeSelectedLayers,
  pasteLayerClipboard,
  renameLayer,
  reorderLayer,
  selectLayer,
  setLayerHidden,
  setLayerLocked,
  subscribeCanvasBridge,
  type CanvasLayerInfo,
  type LayerReorderDirection,
} from "@/lib/canvas-bridge";
import { layerReorderAvailability } from "@/lib/layer-model";

function LayerThumb({ layer }: { layer: CanvasLayerInfo }) {
  if (layer.thumbSrc) {
    return (
      // Canvas asset preview; alt is the layer display name.
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={layer.thumbSrc}
        alt={layer.name}
        className={`h-full w-full object-contain ${layer.hidden ? "opacity-40" : ""}`}
      />
    );
  }
  return (
    <div className="flex h-full w-full items-center justify-center text-faint">
      <ImageIcon size={14} />
    </div>
  );
}

function ReorderButton({
  label,
  disabled,
  onClick,
}: {
  label: string;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      disabled={disabled}
      onClick={(event) => {
        event.stopPropagation();
        onClick();
      }}
      className="rounded px-1 py-0.5 text-[10px] text-muted transition-colors hover:bg-surface-3 hover:text-ink disabled:cursor-not-allowed disabled:opacity-30"
    >
      {label}
    </button>
  );
}

function ToolbarButton({
  label,
  disabled,
  onClick,
}: {
  label: string;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => void onClick()}
      className="rounded-lg border border-line bg-surface-2 px-2 py-1 text-[11px] font-medium text-ink transition-colors hover:bg-surface-3 disabled:cursor-not-allowed disabled:opacity-35"
    >
      {label}
    </button>
  );
}

function LayerRow({
  layer,
  topFirstIndex,
  total,
}: {
  layer: CanvasLayerInfo;
  topFirstIndex: number;
  total: number;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(layer.name);
  const moves = layerReorderAvailability(topFirstIndex, total);

  useEffect(() => {
    if (!editing) setDraft(layer.name);
  }, [layer.name, editing]);

  function commitRename() {
    const next = draft.trim();
    setEditing(false);
    if (!next || next === layer.name) {
      setDraft(layer.name);
      return;
    }
    renameLayer(layer.id, next);
  }

  function move(direction: LayerReorderDirection) {
    reorderLayer(layer.id, direction);
  }

  function handleActivate(event: React.MouseEvent | React.KeyboardEvent) {
    const additive =
      "metaKey" in event
        ? Boolean(event.metaKey || event.ctrlKey || event.shiftKey)
        : false;
    selectLayer(layer.id, { additive });
  }

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={handleActivate}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          handleActivate(event);
        }
      }}
      className={`flex cursor-pointer gap-2 rounded-xl border px-2 py-2 transition-colors ${
        layer.selected
          ? "border-accent bg-surface-2"
          : "border-line bg-surface-2/50 hover:border-accent/40"
      }`}
    >
      <div className="flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-surface-3">
        <LayerThumb layer={layer} />
      </div>

      <div className="min-w-0 flex-1">
        {editing ? (
          <input
            autoFocus
            value={draft}
            onClick={(event) => event.stopPropagation()}
            onChange={(event) => setDraft(event.target.value)}
            onBlur={commitRename}
            onKeyDown={(event) => {
              event.stopPropagation();
              if (event.key === "Enter") commitRename();
              if (event.key === "Escape") {
                setDraft(layer.name);
                setEditing(false);
              }
            }}
            className="w-full rounded border border-accent bg-surface-1 px-1.5 py-0.5 text-xs text-ink outline-none"
          />
        ) : (
          <button
            type="button"
            title="双击重命名；Ctrl/Shift 点击多选"
            className={`block w-full truncate text-left text-xs font-medium ${
              layer.hidden ? "text-muted line-through" : "text-ink"
            }`}
            onClick={(event) => {
              event.stopPropagation();
              handleActivate(event);
            }}
            onDoubleClick={(event) => {
              event.stopPropagation();
              setEditing(true);
            }}
          >
            {layer.name}
          </button>
        )}

        <div className="mt-1 flex flex-wrap items-center gap-0.5">
          <ReorderButton label="置顶" disabled={!moves.front} onClick={() => move("front")} />
          <ReorderButton label="上移" disabled={!moves.up} onClick={() => move("up")} />
          <ReorderButton label="下移" disabled={!moves.down} onClick={() => move("down")} />
          <ReorderButton label="置底" disabled={!moves.back} onClick={() => move("back")} />
        </div>
      </div>

      <div className="flex shrink-0 flex-col gap-1">
        <button
          type="button"
          title={layer.hidden ? "显示" : "隐藏"}
          aria-label={layer.hidden ? "显示图层" : "隐藏图层"}
          onClick={(event) => {
            event.stopPropagation();
            setLayerHidden(layer.id, !layer.hidden);
          }}
          className="rounded-md p-1 text-muted transition-colors hover:bg-surface-3 hover:text-ink"
        >
          {layer.hidden ? <EyeOffIcon size={14} /> : <EyeIcon size={14} />}
        </button>
        <button
          type="button"
          title={layer.locked ? "解锁" : "锁定"}
          aria-label={layer.locked ? "解锁图层" : "锁定图层"}
          onClick={(event) => {
            event.stopPropagation();
            setLayerLocked(layer.id, !layer.locked);
          }}
          className="rounded-md p-1 text-muted transition-colors hover:bg-surface-3 hover:text-ink"
        >
          {layer.locked ? <LockIcon size={14} /> : <UnlockIcon size={14} />}
        </button>
      </div>
    </div>
  );
}

export function LayerPanel() {
  const [layers, setLayers] = useState<CanvasLayerInfo[]>(() => listImageLayers());
  const [clipboardReady, setClipboardReady] = useState(() => hasLayerClipboard());
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    const refresh = () => {
      setLayers(listImageLayers());
      setClipboardReady(hasLayerClipboard());
    };
    refresh();
    return subscribeCanvasBridge(refresh);
  }, []);

  const selectedCount = layers.filter((layer) => layer.selected).length;

  async function runOp(label: string, fn: () => Promise<boolean>) {
    if (busy) return;
    setBusy(true);
    setStatus(null);
    try {
      const ok = await fn();
      setStatus(ok ? null : `${label}失败`);
    } catch (err) {
      setStatus(err instanceof Error ? err.message : `${label}失败`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-surface-1 text-ink">
      <div className="shrink-0 space-y-2 border-b border-line px-3 py-2">
        <p className="text-xs text-muted">
          顶→底列表。Ctrl/Shift 点击多选后可合并；双击名称重命名。
        </p>
        <div className="flex flex-wrap gap-1.5">
          <ToolbarButton
            label="新建"
            disabled={busy}
            onClick={() => void runOp("新建", createBlankLayer)}
          />
          <ToolbarButton
            label="复制"
            disabled={busy || selectedCount === 0}
            onClick={() => void runOp("复制", copySelectedLayer)}
          />
          <ToolbarButton
            label="粘贴"
            disabled={busy || !clipboardReady}
            onClick={() => void runOp("粘贴", pasteLayerClipboard)}
          />
          <ToolbarButton
            label="创建副本"
            disabled={busy || selectedCount === 0}
            onClick={() => void runOp("创建副本", duplicateSelectedLayer)}
          />
          <ToolbarButton
            label="合并"
            disabled={busy || selectedCount < 2}
            onClick={() => void runOp("合并", mergeSelectedLayers)}
          />
        </div>
        {status ? <p className="text-[11px] text-warning">{status}</p> : null}
      </div>

      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-3">
        {layers.length === 0 ? (
          <div className="flex h-40 flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-line text-muted">
            <ImageIcon size={20} />
            <p className="text-xs">画布上还没有图片图层</p>
          </div>
        ) : (
          layers.map((layer, topFirstIndex) => (
            <LayerRow
              key={layer.id}
              layer={layer}
              topFirstIndex={topFirstIndex}
              total={layers.length}
            />
          ))
        )}
      </div>
    </div>
  );
}
