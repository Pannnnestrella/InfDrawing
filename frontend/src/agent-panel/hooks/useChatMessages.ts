import { useCallback, useState } from "react";

import { createMessageId, type ChatMessage } from "@/agent-panel/types";

export function useChatMessages() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  const appendMessage = useCallback((entry: ChatMessage) => {
    setMessages((prev) => [...prev, entry]);
  }, []);

  const appendStatus = useCallback(
    (text: string) => {
      appendMessage({ id: createMessageId(), role: "assistant", kind: "status", text });
    },
    [appendMessage],
  );

  const appendError = useCallback(
    (text: string) => {
      appendMessage({ id: createMessageId(), role: "assistant", kind: "error", text });
    },
    [appendMessage],
  );

  const notifyReconnect = useCallback(
    (attempt: number) => {
      appendStatus(`连接断开，正在重连（第 ${attempt} 次）…`);
    },
    [appendStatus],
  );

  return {
    messages,
    appendMessage,
    appendStatus,
    appendError,
    notifyReconnect,
  };
}
