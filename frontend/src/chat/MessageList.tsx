/**
 * MessageList — message list container.
 *
 * Renders ChatMessage[] as bubbles and follows streaming by auto-scrolling to the
 * bottom — but ONLY when the user is already near the bottom. If the user scrolls up
 * (e.g. to re-read an earlier answer while a new one streams), we stop pinning so they
 * are not yanked back down. Scrolling back to the bottom re-enables following.
 */
import { useEffect, useRef } from 'react';
import type { ChatMessage } from '../types';
import { MessageBubble } from './MessageBubble';

interface Props {
  messages: ChatMessage[];
  onPointClick: (rawRowId: number) => void;
}

// How close to the bottom (px) still counts as "following the stream".
const NEAR_BOTTOM_PX = 80;

export function MessageList({ messages, onPointClick }: Props) {
  const listRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  // Whether the user is currently pinned to the bottom (a ref, to avoid re-renders).
  const atBottomRef = useRef(true);

  const updateAtBottom = () => {
    const el = listRef.current;
    if (!el) return;
    atBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX;
  };

  // Follow the stream only when the user hasn't scrolled away from the bottom.
  useEffect(() => {
    if (atBottomRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  return (
    <div className="message-list" ref={listRef} onScroll={updateAtBottom}>
      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} onPointClick={onPointClick} />
      ))}
      {/* scroll anchor */}
      <div ref={bottomRef} />
    </div>
  );
}
