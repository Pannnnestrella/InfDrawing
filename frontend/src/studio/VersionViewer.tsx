"use client";

import { useState } from "react";

import { Spinner } from "@/components/Spinner";
import {
  PROGRESS_LABELS,
  isVersionBusy,
  type BBox,
  type EditVersion,
  type SceneEntity,
} from "@/lib/controlled-edit-api";

import { DEFAULT_BBOX } from "./bbox-edit";
import { BBoxEditor } from "./BBoxEditor";
import { useArtifactUrl } from "./useArtifactUrl";

interface VersionViewerProps {
  version: EditVersion;
  parent: EditVersion | null;
  highlightedEntity: SceneEntity | null;
  editingEntity: SceneEntity | null;
  savingBBox: boolean;
  onSaveBBox: (bbox: BBox) => void;
  onCancelEdit: () => void;
}

export function VersionViewer({
  version,
  parent,
  highlightedEntity,
  editingEntity,
  savingBBox,
  onSaveBBox,
  onCancelEdit,
}: VersionViewerProps) {
  const busy = isVersionBusy(version);
  const ownUrl = useArtifactUrl(version.image_artifact_id);
  const parentUrl = useArtifactUrl(parent?.image_artifact_id ?? null);
  const [compare, setCompare] = useState(true);
  const [split, setSplit] = useState(50);

  const displayUrl = ownUrl ?? (busy || version.status === "failed" ? parentUrl : null);
  const canCompare = Boolean(ownUrl && parentUrl);
  const editing = Boolean(editingEntity && ownUrl);
  const showCompare = compare && canCompare && !editing;
  const aspect =
    version.width && version.height ? `${version.width} / ${version.height}` : "4 / 3";
  const bbox = highlightedEntity?.bbox;

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <div className="flex shrink-0 items-center justify-between text-[11px] text-muted">
        <span>
          {parent ? "当前版本" : "原图"}
          {version.width ? ` · ${version.width}×${version.height}` : ""}
        </span>
        <label
          className={`flex items-center gap-1.5 ${canCompare ? "cursor-pointer" : "opacity-40"}`}
        >
          <input
            type="checkbox"
            checked={showCompare}
            disabled={!canCompare}
            onChange={(event) => setCompare(event.target.checked)}
          />
          与上一版对比
        </label>
      </div>

      <div className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden rounded-xl border border-line bg-surface-1">
        {displayUrl ? (
          <div
            className="relative max-h-full max-w-full"
            style={{ aspectRatio: aspect, height: "100%" }}
          >
            {/* eslint-disable-next-line @next/next/no-img-element -- blob URLs */}
            <img
              src={displayUrl}
              alt="当前版本"
              className={`absolute inset-0 h-full w-full object-contain ${busy ? "opacity-40" : ""}`}
              draggable={false}
            />
            {showCompare && parentUrl ? (
              <>
                {/* eslint-disable-next-line @next/next/no-img-element -- blob URLs */}
                <img
                  src={parentUrl}
                  alt="上一版"
                  className="absolute inset-0 h-full w-full object-contain"
                  style={{ clipPath: `inset(0 ${100 - split}% 0 0)` }}
                  draggable={false}
                />
                <div
                  className="pointer-events-none absolute inset-y-0 w-0.5 bg-white/80"
                  style={{ left: `${split}%` }}
                />
                <span className="absolute left-2 top-2 rounded bg-black/60 px-1.5 py-0.5 text-[10px]">
                  上一版
                </span>
                <span className="absolute right-2 top-2 rounded bg-black/60 px-1.5 py-0.5 text-[10px]">
                  当前
                </span>
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={split}
                  aria-label="对比分割线"
                  onChange={(event) => setSplit(Number(event.target.value))}
                  className="absolute inset-x-0 bottom-2 mx-auto w-2/3"
                />
              </>
            ) : null}
            {editing && editingEntity ? (
              <BBoxEditor
                key={editingEntity.id}
                initial={editingEntity.bbox ?? DEFAULT_BBOX}
                label={editingEntity.name}
                saving={savingBBox}
                onSave={onSaveBBox}
                onCancel={onCancelEdit}
              />
            ) : null}
            {bbox && !showCompare && !editing ? (
              <div
                className="pointer-events-none absolute rounded border-2 border-accent-hover bg-accent/15"
                style={{
                  left: `${bbox.x * 100}%`,
                  top: `${bbox.y * 100}%`,
                  width: `${bbox.w * 100}%`,
                  height: `${bbox.h * 100}%`,
                }}
              >
                <span className="absolute -top-5 left-0 whitespace-nowrap rounded bg-accent px-1 text-[10px] text-white">
                  {highlightedEntity?.name}
                </span>
              </div>
            ) : null}
          </div>
        ) : (
          <Spinner size={20} />
        )}

        {busy ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-sm">
            <Spinner size={22} />
            <span>{PROGRESS_LABELS[version.progress_step ?? "queued"] ?? "处理中"}</span>
            {version.attempts > 1 ? (
              <span className="text-[11px] text-muted">第 {version.attempts} 次尝试</span>
            ) : null}
          </div>
        ) : null}
        {version.status === "failed" ? (
          <div className="absolute inset-x-4 bottom-4 rounded-lg border border-danger/40 bg-surface-0/90 p-3 text-xs text-danger">
            生成失败：{version.error ?? "未知错误"}。可在修改树中回到上一版重新编辑。
          </div>
        ) : null}
      </div>
    </div>
  );
}
