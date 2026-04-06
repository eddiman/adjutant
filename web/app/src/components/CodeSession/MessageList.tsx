import { useEffect, useRef } from 'react';
import { MessageBubble } from './MessageBubble';
import type { ChatMessage } from '../../hooks/useCodeSession';
import bubbleStyles from './MessageBubble.module.css';

interface MessageListProps {
  messages: ChatMessage[];
  streamingContent: string;
  isStreaming: boolean;
}

export function MessageList({ messages, streamingContent, isStreaming }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new content
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length, streamingContent, isStreaming]);

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '0.5rem 1rem' }}>
      {messages.map(msg => (
        <MessageBubble key={msg.id} message={msg} />
      ))}

      {isStreaming && streamingContent ? (
        <MessageBubble
          message={{
            id: '__streaming__',
            role: 'assistant',
            content: streamingContent,
            timestamp: new Date().toISOString(),
          }}
          isStreaming
        />
      ) : isStreaming ? (
        /* Typing indicator — bouncing dots while waiting for first delta */
        <div className={bubbleStyles.typingIndicator}>
          <span className={bubbleStyles.typingDot} />
          <span className={bubbleStyles.typingDot} />
          <span className={bubbleStyles.typingDot} />
        </div>
      ) : null}

      <div ref={bottomRef} />
    </div>
  );
}
