/**
 * MessageList — 消息列表容器。
 *
 * 职责：
 *  - 渲染 ChatMessage[] → MessageBubble[]
 *  - 每次 messages 变化自动滚到底部（流式追加时跟随）
 *  - 列表为空时显示引导语
 */
import { useEffect, useRef } from 'react';
import type { ChatMessage } from '../types';
import { MessageBubble } from './MessageBubble';

interface Props {
  messages: ChatMessage[];
  onPointClick: (rawRowId: number) => void;
}

export function MessageList({ messages, onPointClick }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // messages 变化（新消息 or 流式追加）时滚到底
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div className="message-list">
      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} onPointClick={onPointClick} />
      ))}
      {/* 滚动锚点 */}
      <div ref={bottomRef} />
    </div>
  );
}
