"use client";

import type { EntityStatus, SceneEntity } from "@/lib/controlled-edit-api";

const STATUS_OPTIONS: { value: EntityStatus; label: string; hint: string }[] = [
  { value: "locked", label: "锁定", hint: "提示词要求严格保持，并附参考图；验收必检" },
  { value: "approved", label: "确认", hint: "无明确指令时保持不变；变化只给警告" },
  { value: "editable", label: "可改", hint: "不额外约束" },
];

const ACTIVE_CLASS: Record<EntityStatus, string> = {
  locked: "bg-danger/20 text-danger",
  approved: "bg-success/20 text-success",
  editable: "bg-surface-3 text-ink",
};

interface EntityPanelProps {
  entities: SceneEntity[];
  disabled: boolean;
  pendingEntityId: string | null;
  editingEntityId: string | null;
  selectedTargetIds: string[];
  onStatusChange: (entityId: string, status: EntityStatus) => void;
  onHover: (entityId: string | null) => void;
  onEditBox: (entityId: string) => void;
  onToggleTarget: (entityId: string) => void;
}

function orderAsTree(entities: SceneEntity[]): { entity: SceneEntity; depth: number }[] {
  const ids = new Set(entities.map((e) => e.id));
  const children = new Map<string | null, SceneEntity[]>();
  for (const entity of entities) {
    const key = entity.parent_id && ids.has(entity.parent_id) ? entity.parent_id : null;
    children.set(key, [...(children.get(key) ?? []), entity]);
  }
  const rows: { entity: SceneEntity; depth: number }[] = [];
  const walk = (parent: string | null, depth: number) => {
    for (const entity of children.get(parent) ?? []) {
      rows.push({ entity, depth });
      walk(entity.id, depth + 1);
    }
  };
  walk(null, 0);
  return rows;
}

function hasLockedAncestor(entities: SceneEntity[], entityId: string): boolean {
  const byId = new Map(entities.map((entity) => [entity.id, entity]));
  let current = byId.get(entityId);
  while (current?.parent_id) {
    const parent = byId.get(current.parent_id);
    if (!parent) break;
    if (parent.status === "locked") return true;
    current = parent;
  }
  return false;
}

export function EntityPanel({
  entities,
  disabled,
  pendingEntityId,
  editingEntityId,
  selectedTargetIds,
  onStatusChange,
  onHover,
  onEditBox,
  onToggleTarget,
}: EntityPanelProps) {
  const rows = orderAsTree(entities);
  const lockedCount = entities.filter((e) => e.status === "locked").length;

  return (
    <section className="flex h-full min-h-0 flex-col">
      <header className="mb-2 flex items-baseline justify-between">
        <h2 className="text-xs font-semibold tracking-wide">场景实体</h2>
        <span className="text-[10px] text-faint">
          {entities.length} 个 · 锁定 {lockedCount}
        </span>
      </header>
      {rows.length === 0 ? (
        <p className="text-[11px] text-muted">暂无实体</p>
      ) : (
        <ul className="panel-scroll -mr-1 min-h-0 flex-1 space-y-0.5 overflow-y-auto pr-1">
          {rows.map(({ entity, depth }) => {
            const inherited = hasLockedAncestor(entities, entity.id);
            const statusLocked = disabled || pendingEntityId === entity.id || inherited;
            return (
              <li
                key={entity.id}
                className={`flex items-center justify-between gap-2 rounded-md px-1.5 py-1 hover:bg-surface-2 ${
                  selectedTargetIds.includes(entity.id) ? "ring-1 ring-accent/70 bg-accent/5" : ""
                }`}
                style={{ paddingLeft: `${6 + depth * 14}px` }}
                onMouseEnter={() => onHover(entity.id)}
                onMouseLeave={() => onHover(null)}
              >
                <button
                  type="button"
                  className="min-w-0 text-left"
                  title="点选后，下一条指令会改这个实体"
                  disabled={disabled}
                  onClick={() => onToggleTarget(entity.id)}
                >
                  <div className="truncate text-xs">
                    {entity.name}
                    {entity.status === "locked" && !entity.anchor_artifact_id ? (
                      <span
                        className="ml-1 text-[10px] text-warning"
                        title={inherited ? "随父节点锁定，无独立参考图" : "无 bbox，仅提示词约束"}
                      >
                        {inherited ? "随父锁定" : "无参考图"}
                      </span>
                    ) : null}
                    {entity.bbox_source === "manual" ? (
                      <span className="ml-1 text-[10px] text-accent-hover" title="框已手动校正">
                        手动
                      </span>
                    ) : null}
                  </div>
                  <div className="truncate text-[10px] text-faint">
                    {entity.id}
                    {selectedTargetIds.includes(entity.id) ? " · 本轮目标" : ""}
                  </div>
                </button>
                <div className="flex shrink-0 gap-0.5 rounded-md bg-surface-1 p-0.5">
                  <button
                    type="button"
                    title={entity.bbox ? "手动调整这个实体的框" : "这个实体没有框，手动画一个"}
                    disabled={disabled || pendingEntityId === entity.id}
                    onClick={() => onEditBox(entity.id)}
                    className={`rounded px-1.5 py-0.5 text-[10px] transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                      editingEntityId === entity.id
                        ? "bg-warning/20 text-warning"
                        : "text-muted hover:text-ink"
                    }`}
                  >
                    框
                  </button>
                  {STATUS_OPTIONS.map((option) => {
                    const active = entity.status === option.value;
                    return (
                      <button
                        key={option.value}
                        type="button"
                        title={
                          inherited
                            ? "随父节点锁定，请先解锁父节点"
                            : option.hint
                        }
                        disabled={statusLocked}
                        onClick={() => !active && onStatusChange(entity.id, option.value)}
                        className={`rounded px-1.5 py-0.5 text-[10px] transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                          active ? ACTIVE_CLASS[option.value] : "text-muted hover:text-ink"
                        }`}
                      >
                        {option.label}
                      </button>
                    );
                  })}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
