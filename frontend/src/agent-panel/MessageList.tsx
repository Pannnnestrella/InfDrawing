"use client";

import { useEffect, useRef } from "react";

import { AlertIcon, SparklesIcon } from "@/components/icons";
import { Spinner } from "@/components/Spinner";

import { MODE_LABELS, type ChatMessage } from "./types";

interface MessageListProps {
  messages: ChatMessage[];
  busy: boolean;
}

export function MessageList({ messages, busy }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 px-8 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-surface-2 text-accent">
          <SparklesIcon size={22} />
        </div>
        <div>
          <p className="text-sm font-medium text-ink">AI 创作面板</p>
          <p className="mt-1 text-xs leading-relaxed text-muted">
            选择下方功能并输入提示词，
            <br />
            或在画布上右键唤起 AI 生图 / 元素拆解
          </p>
        </div>
      </div>
    );
  }

  const lastIndex = messages.length - 1;

  return (
    <div className="panel-scroll flex min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto px-4 py-3">
      {messages.map((msg, index) => {
        if (msg.role === "user") {
          return (
            <div key={msg.id} className="flex justify-end">
              <div className="max-w-[85%] rounded-2xl rounded-br-md bg-accent px-3.5 py-2 text-sm text-white shadow-sm">
                <p className="mb-0.5 text-[10px] font-medium uppercase tracking-wide opacity-75">
                  {MODE_LABELS[msg.mode]}
                </p>
                <p className="whitespace-pre-wrap leading-relaxed">{msg.text}</p>
              </div>
            </div>
          );
        }

        if (msg.kind === "error") {
          return (
            <div key={msg.id} className="flex items-start gap-2 pr-6">
              <AlertIcon size={14} className="mt-0.5 shrink-0 text-danger" />
              <p className="text-xs leading-relaxed text-danger">{msg.text}</p>
            </div>
          );
        }

        if (msg.kind === "image") {
          return (
            <div key={msg.id} className="flex justify-start">
              <div className="max-w-[85%] overflow-hidden rounded-xl border border-line bg-surface-2 shadow-sm">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={msg.imageUrl}
                  alt={msg.caption ?? "生成结果"}
                  className="max-h-44 w-full object-contain"
                />
                {msg.caption ? (
                  <p className="border-t border-line px-2.5 py-1.5 text-[11px] text-muted">
                    {msg.caption}
                  </p>
                ) : null}
              </div>
            </div>
          );
        }

        const activeTask = busy && index === lastIndex;
        return (
          <div key={msg.id} className="space-y-1.5 pr-6">
            <div className="flex items-center gap-2">
              {activeTask ? (
                <Spinner size={12} />
              ) : (
                <span className="h-1 w-1 shrink-0 rounded-full bg-faint" />
              )}
              <p className="text-xs leading-relaxed text-muted">{msg.text}</p>
            </div>
            {activeTask ? (
              <div className="ml-5 h-0.5 w-40 overflow-hidden rounded-full bg-surface-3">
                <div className="progress-indeterminate h-full w-1/3 rounded-full bg-accent" />
              </div>
            ) : null}
          </div>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}
