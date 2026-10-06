export const ASSET_TYPES = {
  character: "角色",
  creature: "生物",
  weapon: "武器",
  armor: "防具",
  prop: "道具",
  item: "物品",
  environment: "场景",
  architecture: "建筑",
  vehicle: "载具",
  ui: "界面",
  icon: "图标",
  vfx: "特效",
  concept: "概念图",
  other: "其他",
} as const;

export const VIEWS = {
  full_body: "全身",
  bust: "半身",
  face: "头像",
  three_quarter: "四分之三侧",
  side: "侧面",
  back: "背面",
  isometric: "等距",
  top_down: "俯视",
  close_up: "特写",
  scene: "场景构图",
  other: "其他",
} as const;

export const GENRES = {
  fantasy: "奇幻",
  scifi: "科幻",
  modern: "现代",
  historical: "历史",
  eastern: "东方",
  horror: "恐怖",
  anime: "二次元",
  other: "其他",
} as const;

export const BACKGROUNDS = {
  environment: "实景/环境",
  studio: "棚拍/灰底",
  transparent: "透明底",
  solid: "纯色底",
  sky: "天空",
  other: "其他",
} as const;

export const POSES = {
  standing: "站立",
  action: "动作",
  idle: "待机",
  sitting: "坐/跪",
  flying: "飞行",
  none: "无（非角色）",
  other: "其他",
} as const;

export type CatalogMap = Readonly<Record<string, string>>;

export function catalogLabel(catalog: CatalogMap, code: string): string {
  if (!code) return "";
  return catalog[code] ?? code;
}

export function catalogSearchBlob(catalog: CatalogMap, code: string): string {
  const label = catalogLabel(catalog, code);
  return [code, label].filter(Boolean).join(" ");
}
