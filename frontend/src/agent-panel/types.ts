import type { IntentType } from "@/lib/api";

export type ManualChatMode = IntentType;
export type ChatMode = "auto" | ManualChatMode;

export type ChatMessage =
  | {
      id: string;
      role: "user";
      mode: ChatMode;
      text: string;
    }
  | {
      id: string;
      role: "assistant";
      kind: "status";
      text: string;
    }
  | {
      id: string;
      role: "assistant";
      kind: "error";
      text: string;
    }
  | {
      id: string;
      role: "assistant";
      kind: "clarification";
      text: string;
    }
  | {
      id: string;
      role: "assistant";
      kind: "image";
      imageUrl: string;
      caption?: string;
    };

export const MODE_LABELS: Record<ChatMode, string> = {
  auto: "自动",
  txt2img: "生图",
  inpaint: "局部重绘",
  image_edit: "指令改图",
  decompose: "元素拆解",
  text_edit: "文字编辑",
};

export const MODE_ORDER: ChatMode[] = [
  "auto",
  "txt2img",
  "inpaint",
  "image_edit",
  "decompose",
  "text_edit",
];

export function createMessageId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}
