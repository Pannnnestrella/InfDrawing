import type { EditVersion } from "@/lib/controlled-edit-api";

export interface TreeNodeLayout {
  version: EditVersion;
  /** Generation index from the root (0 = root); rendered as the x axis. */
  depth: number;
  /** Branch lane; the first child continues its parent's lane. */
  lane: number;
  /** 1-based creation order, used as a short label ("v3"). */
  ordinal: number;
}

export interface TreeEdgeLayout {
  from: TreeNodeLayout;
  to: TreeNodeLayout;
}

export interface TreeLayout {
  nodes: TreeNodeLayout[];
  edges: TreeEdgeLayout[];
  depthCount: number;
  laneCount: number;
}

/**
 * Lay out a version DAG like a git graph: generations go left-to-right, the
 * first child stays on its parent's lane and later siblings open new lanes.
 */
export function layoutVersionTree(versions: EditVersion[]): TreeLayout {
  const ordered = [...versions].sort((a, b) => a.created_at.localeCompare(b.created_at));
  const ordinals = new Map(ordered.map((v, index) => [v.id, index + 1]));
  const ids = new Set(ordered.map((v) => v.id));
  const children = new Map<string, EditVersion[]>();
  const roots: EditVersion[] = [];
  for (const version of ordered) {
    if (version.parent_id && ids.has(version.parent_id)) {
      const siblings = children.get(version.parent_id) ?? [];
      siblings.push(version);
      children.set(version.parent_id, siblings);
    } else {
      roots.push(version);
    }
  }

  const nodes: TreeNodeLayout[] = [];
  const byId = new Map<string, TreeNodeLayout>();
  let nextLane = 0;
  let maxDepth = 0;

  const visit = (version: EditVersion, depth: number, lane: number) => {
    const node: TreeNodeLayout = {
      version,
      depth,
      lane,
      ordinal: ordinals.get(version.id) ?? 0,
    };
    nodes.push(node);
    byId.set(version.id, node);
    maxDepth = Math.max(maxDepth, depth);
    (children.get(version.id) ?? []).forEach((child, index) => {
      visit(child, depth + 1, index === 0 ? lane : ++nextLane);
    });
  };

  roots.forEach((root, index) => visit(root, 0, index === 0 ? nextLane : ++nextLane));

  const edges: TreeEdgeLayout[] = [];
  for (const node of nodes) {
    const parent = node.version.parent_id ? byId.get(node.version.parent_id) : undefined;
    if (parent) edges.push({ from: parent, to: node });
  }
  return {
    nodes,
    edges,
    depthCount: nodes.length ? maxDepth + 1 : 0,
    laneCount: nodes.length ? nextLane + 1 : 0,
  };
}

/** Versions from the root down to `versionId`, inclusive. */
export function ancestryPath(versions: EditVersion[], versionId: string | null): string[] {
  const byId = new Map(versions.map((v) => [v.id, v]));
  const path: string[] = [];
  let current = versionId ? byId.get(versionId) : undefined;
  while (current && !path.includes(current.id)) {
    path.unshift(current.id);
    current = current.parent_id ? byId.get(current.parent_id) : undefined;
  }
  return path;
}
