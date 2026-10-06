"use client";

import { useMemo } from "react";

import { isVersionBusy, type EditVersion } from "@/lib/controlled-edit-api";

import { ancestryPath, layoutVersionTree, type TreeNodeLayout } from "./version-tree-layout";

const COL = 72;
const ROW = 52;
const PAD = 28;
const RADIUS = 15;

interface VersionTreeProps {
  versions: EditVersion[];
  currentVersionId: string | null;
  disabled?: boolean;
  onSelect: (versionId: string) => void;
}

function nodeColor(version: EditVersion): string {
  if (version.status === "failed") return "var(--color-danger)";
  if (isVersionBusy(version)) return "var(--color-accent)";
  if (version.warnings.length > 0) return "var(--color-warning)";
  return "var(--color-success)";
}

function nodeTitle(node: TreeNodeLayout): string {
  const { version } = node;
  const head = node.depth === 0 ? "原图" : (version.instruction ?? "");
  const status =
    version.status === "failed"
      ? "失败"
      : isVersionBusy(version)
        ? "生成中"
        : version.warnings.length
          ? `${version.warnings.length} 条警告`
          : "验收通过";
  return `v${node.ordinal} · ${head}\n${node.depth === 0 ? "" : status}`.trim();
}

export function VersionTree({ versions, currentVersionId, disabled, onSelect }: VersionTreeProps) {
  const layout = useMemo(() => layoutVersionTree(versions), [versions]);
  const path = useMemo(
    () => new Set(ancestryPath(versions, currentVersionId)),
    [versions, currentVersionId],
  );
  const x = (depth: number) => PAD + depth * COL;
  const y = (lane: number) => PAD + lane * ROW;
  const width = PAD * 2 + Math.max(0, layout.depthCount - 1) * COL;
  const height = PAD * 2 + Math.max(0, layout.laneCount - 1) * ROW;

  return (
    <div className="panel-scroll h-full overflow-auto">
      <svg width={width} height={height} role="tree" aria-label="修改树">
        {layout.edges.map(({ from, to }) => {
          const x1 = x(from.depth);
          const y1 = y(from.lane);
          const x2 = x(to.depth);
          const y2 = y(to.lane);
          const d =
            y1 === y2
              ? `M ${x1} ${y1} L ${x2} ${y2}`
              : `M ${x1} ${y1} C ${x1 + COL * 0.6} ${y1}, ${x2 - COL * 0.6} ${y2}, ${x2} ${y2}`;
          const onPath = path.has(from.version.id) && path.has(to.version.id);
          return (
            <path
              key={`${from.version.id}-${to.version.id}`}
              d={d}
              fill="none"
              stroke={onPath ? "var(--color-accent-hover)" : "var(--color-line-strong)"}
              strokeWidth={onPath ? 2.5 : 1.5}
            />
          );
        })}
        {layout.nodes.map((node) => {
          const { version } = node;
          const current = version.id === currentVersionId;
          const busy = isVersionBusy(version);
          return (
            <g
              key={version.id}
              role="treeitem"
              aria-selected={current}
              tabIndex={disabled ? -1 : 0}
              transform={`translate(${x(node.depth)} ${y(node.lane)})`}
              className={disabled ? "cursor-not-allowed" : "cursor-pointer"}
              onClick={() => !disabled && onSelect(version.id)}
              onKeyDown={(event) => {
                if (!disabled && (event.key === "Enter" || event.key === " ")) onSelect(version.id);
              }}
            >
              <title>{nodeTitle(node)}</title>
              {current ? (
                <circle r={RADIUS + 5} fill="none" stroke="var(--color-accent-hover)" strokeWidth={2} />
              ) : null}
              <circle
                r={RADIUS}
                fill="var(--color-surface-2)"
                stroke={nodeColor(version)}
                strokeWidth={2.5}
                className={busy ? "animate-pulse" : undefined}
              />
              <text
                textAnchor="middle"
                dominantBaseline="central"
                fontSize={11}
                fontWeight={600}
                fill="var(--color-ink)"
              >
                {`v${node.ordinal}`}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
