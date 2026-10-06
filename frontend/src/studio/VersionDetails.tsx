"use client";

import type { EditVersion } from "@/lib/controlled-edit-api";

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

function ReferenceThumb({ artifactId, index }: { artifactId: string; index: number }) {
  const url = useArtifactUrl(artifactId);
  return (
    <figure className="w-14 shrink-0 text-center">
      <div className="h-14 w-14 overflow-hidden rounded border border-line bg-surface-1">
        {url ? (
          // eslint-disable-next-line @next/next/no-img-element -- blob URLs
          <img src={url} alt={`参考图 ${index}`} className="h-full w-full object-cover" />
        ) : null}
      </div>
      <figcaption className="mt-0.5 text-[9px] text-faint">图 {index}</figcaption>
    </figure>
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

interface VersionDetailsProps {
  version: EditVersion;
  entityNames: Record<string, string>;
}

export function VersionDetails({ version, entityNames }: VersionDetailsProps) {
  if (!version.parent_id) {
    return (
      <section className="text-[11px] text-muted">
        原图节点。锁定或确认实体后输入指令，即可生成第一个修改版本。
      </section>
    );
  }
  const { intent, verification } = version;

  return (
    <section className="space-y-3 text-[11px]">
      <div>
        <h2 className="mb-1 text-xs font-semibold tracking-wide">本轮修改</h2>
        <p className="text-ink">{version.instruction}</p>
        {intent ? (
          <p className="mt-1 text-muted">
            <span className="mr-1 rounded bg-surface-3 px-1 py-0.5 text-[10px]">
              {OPERATION_LABELS[intent.operation] ?? intent.operation}
            </span>
            {intent.change_description}
          </p>
        ) : null}
        {version.prompt_style || version.image_provider ? (
          <p className="mt-1 text-faint">
            {version.prompt_style
              ? `策略：${promptStyleLabel(version.prompt_style)}`
              : null}
            {version.prompt_style && version.image_provider ? " · " : null}
            {version.image_provider
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

      {version.reference_artifact_ids.length ? (
        <div>
          <h3 className="mb-1 font-semibold">参考图锚定</h3>
          <div className="flex gap-1.5 overflow-x-auto">
            {version.reference_artifact_ids.map((id, index) => (
              <ReferenceThumb key={id} artifactId={id} index={index + 2} />
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
    </section>
  );
}
