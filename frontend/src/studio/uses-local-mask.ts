import type { SceneEntity } from "@/lib/controlled-edit-api";

function area(entity: SceneEntity): number {
  if (!entity.bbox) return 0;
  return entity.bbox.w * entity.bbox.h;
}

function isBackgroundId(entityId: string): boolean {
  const root = entityId.split(".", 1)[0];
  return root === "environment" || root === "foreground";
}

function isWholeSubjectId(entityId: string): boolean {
  return !entityId.includes(".") && !isBackgroundId(entityId);
}

/** Mirror backend ``uses_local_mask`` for Studio routing hints. */
export function usesLocalMask(targets: SceneEntity[]): boolean {
  if (!targets.length) return false;
  for (const entity of targets) {
    if (isBackgroundId(entity.id) || isWholeSubjectId(entity.id)) return false;
    if (!entity.bbox) return false;
    if (area(entity) > 0.25) return false;
  }
  return true;
}
