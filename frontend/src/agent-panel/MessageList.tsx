"use client";

import { useEffect, useRef } from "react";

import { theme } from "@/lib/theme";

import { MODE_LABELS, type ChatMessage } from "./types";

interface MessageListProps {
  messages: ChatMessage[];
}

export function MessageList({ messages }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div
        className="flex flex-1 items-center justify-center px-4 text-center text-sm"
        style={{ color: theme.textMuted }}
      >
        选择功能按钮，输入提示词并发送
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-4 py-3">
      {messages.map((msg) => {
        if (msg.role === "user") {
          return (
            <div key={msg.id} className="flex justify-end">
              <div
                className="max-w-[90%] rounded-lg rounded-tr-sm px-3 py-2 text-sm"
                style={{ background: theme.accent, color: "#fff" }}
              >
                <p className="mb-1 text-[10px] opacity-80">{MODE_LABELS[msg.mode]}</p>
                <p className="whitespace-pre-wrap">{msg.text}</p>
              </div>
            </div>
          );
        }

        if (msg.kind === "error") {
          return (
            <div key={msg.id} className="flex justify-start">
              <p className="max-w-[90%] text-sm text-red-400">{msg.text}</p>
            </div>
          );
        }

        if (msg.kind === "image") {
          return (
            <div key={msg.id} className="flex justify-start">
              <div
                className="max-w-[90%] overflow-hidden rounded-lg border"
                style={{ borderColor: theme.border, background: theme.surface }}
              >
                {msg.caption ? (
                  <p className="px-2 py-1 text-[11px]" style={{ color: theme.textMuted }}>
                    {msg.caption}
                  </p>
                ) : null}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={msg.imageUrl} alt="result" className="max-h-40 w-full object-contain" />
              </div>
            </div>
          );
        }

        return (
          <div key={msg.id} className="flex justify-start">
            <p className="max-w-[90%] text-sm" style={{ color: theme.textMuted }}>
              {msg.text}
            </p>
          </div>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}
