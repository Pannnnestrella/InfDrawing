"use client";

import { useEffect, useState } from "react";

import type { EditVersion, SentImage } from "@/lib/controlled-edit-api";

import { imageProviderLabel, promptStyleLabel } from "./studio-turn-options";
import { useArtifactUrl } from "./useArtifactUrl";

const OPERATION_LABELS: Record<string, string> = {
  add: "添加",
  remove: "移除",
  replace: "替换",
  restyle: "改风格",
  recolor: "改颜色",
  other: "其他",
};

function SentThumb({
  item,
  onOpen,
}: {
  item: SentImage;
  onOpen: (item: SentImage, url: string) => void;
}) {
  const url = useArtifactUrl(item.artifact_id);
  const caption =
    item.index != null ? `图 ${item.index}` : item.role === "mask" ? "Mask" : item.role;
  return (
    <figure className="w-16 shrink-0 text-center">
      <button
        type="button"
        disabled={!url}
        onClick={() => {
          if (url) onOpen(item, url);
        }}
        className={`relative h-14 w-14 overflow-hidden rounded border disabled:opacity-40 ${
          item.role === "mask" ? "bg-black" : "bg-checkerboard"
        } ${
          item.sent ? "border-line hover:border-accent" : "border-dashed border-faint opacity-80"
        }`}
        title={item.label || caption}
      >
        {url ? (
          // eslint-disable-next-line @next/next/no-img-element -- blob URLs
          <img
            src={url}
            alt={item.label || caption}
            className={`h-full w-full ${item.role === "mask" ? "object-contain" : "object-cover"}`}
          />
        ) : null}
        {!item.sent ? (
          <span className="absolute inset-x-0 bottom-0 bg-black/55 px-0.5 text-[8px] text-white">
            未发送
          </span>
        ) : null}
      </button>
      <figcaption className="mt-0.5 line-clamp-2 text-[9px] text-faint" title={item.label}>
        {caption}
      </figcaption>
    </figure>
  );
}

function ImageLightbox({
  item,
  url,
  onClose,
}: {
  item: SentImage;
  url: string;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={item.label || "发送图像预览"}
      className="fixed inset-0 z-[80] flex items-center justify-center bg-black/70 p-4"
      onClick={onClose}
    >
      <div
        className="max-h-[90vh] max-w-[90vw] overflow-auto rounded-lg bg-surface-0 p-3 shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-2 flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold text-ink">
              {item.index != null ? `图 ${item.index} · ` : ""}
              {item.label || item.role}
            </p>
            <p className="text-[10px] text-faint">
              {item.sent ? "已发送给 API" : "未发送给生图 API（锁定锚点，供身份/验收）"}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded px-2 py-1 text-xs text-muted hover:bg-surface-2"
          >
            关闭
          </button>
        </div>
        {/* eslint-disable-next-line @next/next/no-img-element -- blob URLs */}
        <img
          src={url}
          alt={item.label || "payload"}
          className={`max-h-[80vh] max-w-[85vw] object-contain ${
            item.role === "mask" ? "bg-black" : "bg-checkerboard"
          }`}
        />
      </div>
    </div>
  );
}

function ScoreRow({
  label,
  score,
  comment,
  passAt,
}: {
  label: string;
  score: number;
  comment: string;
  passAt: number;
}) {
  return (
    <li title={comment}>
      <div className="flex justify-between">
        <span>{label}</span>
        <span className="tabular-nums text-muted">{score.toFixed(2)}</span>
      </div>
      <div className="mt-0.5 h-1 overflow-hidden rounded bg-surface-3">
        <div
          className={`h-full ${score >= passAt ? "bg-success" : "bg-danger"}`}
          style={{ width: `${score * 100}%` }}
        />
      </div>
    </li>
  );
}

function legacySentImages(version: EditVersion): SentImage[] {
  return version.reference_artifact_ids.map((id, index) => ({
    role: "reference",
    artifact_id: id,
    index: index + 2,
    label: `参考图 ${index + 2}`,
    sent: true,
  }));
}

interface VersionDetailsProps {
  version: EditVersion;
  entityNames: Record<string, string>;
}

export function VersionDetails({ version, entityNames }: VersionDetailsProps) {
  const [preview, setPreview] = useState<{ item: SentImage; url: string } | null>(null);

  if (!version.parent_id) {
    return (
      <section className="text-[11px] text-muted">
        原图节点。锁定或确认实体后输入指令，即可生成第一个修改版本。
      </section>
    );
  }
  const { intent, verification } = version;
  const sent =
    version.sent_images && version.sent_images.length > 0
      ? version.sent_images
      : legacySentImages(version);
  const usedWanx = version.warnings.some((w) => w.includes("local_mask:wanx"));

  return (
    <section className="space-y-3 text-[11px]">
      {version.stitcher ? (
        <p className="text-muted">
          局部 Crop/Stitch · 万相 2.1 · 裁剪 {version.stitcher.crop_rect.join(", ")}
          {" · 工作尺寸 "}
          {version.stitcher.model_size.join("×")}
          {version.stitcher.actual_output_size
            ? ` · 实际输出 ${version.stitcher.actual_output_size.join("×")}`
            : ""}
        </p>
      ) : null}
      <div>
        <h2 className="mb-1 text-xs font-semibold tracking-wide">本轮修改</h2>
        <p className="text-ink">{version.instruction}</p>
        {version.input_version_ids && version.input_version_ids.length > 1 ? (
          <p className="mt-1 text-faint">
            合并来源 {version.input_version_ids.length} 个版本（树边仅显示主父节点）
          </p>
        ) : null}
        {intent ? (
          <p className="mt-1 text-muted">
            <span className="mr-1 rounded bg-surface-3 px-1 py-0.5 text-[10px]">
              {OPERATION_LABELS[intent.operation] ?? intent.operation}
            </span>
            {intent.change_description}
          </p>
        ) : null}
        {version.prompt_style || version.image_provider || usedWanx ? (
          <p className="mt-1 text-faint">
            {version.prompt_style ? `策略：${promptStyleLabel(version.prompt_style)}` : null}
            {version.prompt_style && (version.image_provider || usedWanx) ? " · " : null}
            {usedWanx
              ? "模型：万相 wanx2.1-imageedit（局部 Mask）"
              : version.image_model
                ? `模型：${version.image_model}`
                : version.image_provider
                  ? `模型：${imageProviderLabel(version.image_provider)}`
                  : null}
          </p>
        ) : null}
      </div>

      {verification ? (
        <div>
          <h3 className="mb-1 flex items-center gap-2 font-semibold">
            VLM 验收
            <span
              className={`rounded px-1.5 py-0.5 text-[10px] ${
                verification.passed ? "bg-success/20 text-success" : "bg-danger/20 text-danger"
              }`}
            >
              {verification.passed ? "通过" : "未通过"}
            </span>
            <span className="font-normal text-faint">尝试 {version.attempts} 次</span>
          </h3>
          <p className="text-muted">
            改动{verification.target_applied ? "已生效" : "未生效"}
            {verification.target_comment ? `：${verification.target_comment}` : ""}
          </p>
          <ul className="mt-1.5 space-y-1">
            {verification.composition_score !== null ? (
              <ScoreRow
                label="构图"
                score={verification.composition_score}
                comment={verification.composition_comment}
                passAt={0.75}
              />
            ) : null}
            {verification.preserved.map((item) => (
              <ScoreRow
                key={item.entity_id}
                label={entityNames[item.entity_id] ?? item.entity_id}
                score={item.score}
                comment={item.comment}
                passAt={0.7}
              />
            ))}
          </ul>
        </div>
      ) : null}

      {version.warnings.length ? (
        <ul className="space-y-1 rounded-lg border border-warning/30 bg-warning/5 p-2 text-warning">
          {version.warnings.map((warning) => (
            <li key={warning}>· {warning}</li>
          ))}
        </ul>
      ) : null}

      {sent.length ? (
        <div>
          <h3 className="mb-1 font-semibold">本轮发送的图像</h3>
          <p className="mb-1.5 text-[10px] text-faint">点击缩略图可查看全图 / Mask</p>
          <div className="flex gap-1.5 overflow-x-auto">
            {sent.map((item) => (
              <SentThumb
                key={`${item.role}-${item.artifact_id}-${item.index ?? "x"}`}
                item={item}
                onOpen={(next, url) => setPreview({ item: next, url })}
              />
            ))}
          </div>
        </div>
      ) : null}

      {version.compiled_prompt ? (
        <details open>
          <summary className="cursor-pointer font-semibold text-muted hover:text-ink">
            实际发送的提示词
          </summary>
          <pre className="mt-1 whitespace-pre-wrap rounded-lg bg-surface-1 p-2 font-mono text-[10px] leading-relaxed text-muted">
            {version.compiled_prompt}
          </pre>
        </details>
      ) : null}

      {preview ? (
        <ImageLightbox item={preview.item} url={preview.url} onClose={() => setPreview(null)} />
      ) : null}
    </section>
  );
}
