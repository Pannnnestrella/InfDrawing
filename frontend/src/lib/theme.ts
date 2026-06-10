export const theme = {
  background: "#0D0D0F",
  surface: "#1A1A1F",
  border: "#2A2A32",
  textPrimary: "#E8E8ED",
  textMuted: "#8B8B96",
  accent: "#6C5CE7",
  canvasBg: "#18181C",
} as const;

/** HTTP API base. Browser dev uses same-origin proxy (see next.config rewrites). */
export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ??
  (typeof window !== "undefined" ? "" : "http://127.0.0.1:8000");

/** WebSocket base — always hits backend directly (Next.js rewrite does not proxy WS). */
export const WS_BASE =
  process.env.NEXT_PUBLIC_WS_BASE ??
  process.env.NEXT_PUBLIC_API_BASE ??
  "http://127.0.0.1:8000";
