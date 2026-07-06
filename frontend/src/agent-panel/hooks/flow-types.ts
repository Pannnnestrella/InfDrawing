import type { ChatMessage } from "@/agent-panel/types";

/** Shared callbacks passed into per-mode generate flows. */
export interface FlowCallbacks {
  appendMessage: (entry: ChatMessage) => void;
  appendStatus: (text: string) => void;
  appendError: (text: string) => void;
  notifyReconnect: (attempt: number) => void;
  setBusy: (busy: boolean) => void;
}
