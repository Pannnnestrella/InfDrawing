import { useState } from "react";

const KEYS = {
  aside: "infd.cedit.split.aside",
  tree: "infd.cedit.split.tree",
  entities: "infd.cedit.split.entities",
  details: "infd.cedit.split.details",
} as const;

export const SPLIT_DEFAULTS = {
  aside: 320,
  tree: 160,
  entities: 240,
  details: 200,
} as const;

export const SPLIT_MIN = {
  aside: 220,
  tree: 96,
  entities: 120,
  details: 88,
  preview: 200,
  composer: 140,
} as const;

function storage(): Storage | null {
  return typeof window === "undefined" ? null : window.sessionStorage;
}

export function loadSplitSize(slot: keyof typeof KEYS, fallback: number, min: number): number {
  const raw = storage()?.getItem(KEYS[slot]);
  if (!raw) return fallback;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? Math.max(min, Math.round(parsed)) : fallback;
}

export function saveSplitSize(slot: keyof typeof KEYS, size: number): void {
  storage()?.setItem(KEYS[slot], String(Math.round(size)));
}

export function useSplitSize(
  slot: keyof typeof KEYS,
  fallback: number,
  min: number,
): [number, (size: number) => void] {
  const [size, setSize] = useState(() => loadSplitSize(slot, fallback, min));
  return [
    size,
    (next: number) => {
      setSize(next);
      saveSplitSize(slot, next);
    },
  ];
}
