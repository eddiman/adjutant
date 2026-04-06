import { memo, useCallback } from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { CodeBlock } from './CodeBlock';
import type { ChatMessage } from '../../hooks/useCodeSession';
import styles from './MessageBubble.module.css';

interface MessageBubbleProps {
  message: ChatMessage;
  isStreaming?: boolean;
}

export const MessageBubble = memo(function MessageBubble({ message, isStreaming }: MessageBubbleProps) {
  const renderCode = useCallback(({ className, children, ...props }: React.HTMLAttributes<HTMLElement> & { node?: unknown }) => {
    const match = /language-(\w+)/.exec(className || '');
    const code = String(children).replace(/\n$/, '');

    // Inline code (no language class, short content)
    if (!match && !code.includes('\n')) {
      return <code className={className} {...props}>{children}</code>;
    }

    return <CodeBlock code={code} language={match?.[1]} />;
  }, []);
  if (message.role === 'system') {
    return (
      <div className={`${styles.message} ${styles.system}`}>
        {message.content}
      </div>
    );
  }

  const roleClass = message.role === 'user' ? styles.user : styles.assistant;
  const d = new Date(message.timestamp);
  const dd = String(d.getDate()).padStart(2, '0');
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const yy = String(d.getFullYear()).slice(-2);
  const hh = String(d.getHours()).padStart(2, '0');
  const min = String(d.getMinutes()).padStart(2, '0');
  const time = `${dd}.${mm}.${yy} ${hh}:${min}`;

  return (
    <div className={`${styles.message} ${roleClass}`}>
      <div className={styles.content}>
        {message.role === 'user' ? (
          <p>{message.content}</p>
        ) : (
          <Markdown
            remarkPlugins={[remarkGfm]}
            components={{ code: renderCode }}
          >
            {message.content}
          </Markdown>
        )}
        {isStreaming && <span className={styles.streamingCursor} />}
      </div>

      <div className={styles.meta}>
        <span className={styles.timestamp}>{time}</span>
        {message.role === 'assistant' && !isStreaming && (
          message.error ? (
            <span className={styles.errorBadge}>{message.error}</span>
          ) : (
            <>
              <span className={styles.metaDot} />
              {message.model && <span>{message.model}</span>}
              {message.durationMs != null && (
                <span>{(message.durationMs / 1000).toFixed(1)}s</span>
              )}
              {message.costUsd != null && (
                <span>${message.costUsd.toFixed(4)}</span>
              )}
              {message.inputTokens != null && message.outputTokens != null && (
                <span>{message.inputTokens + message.outputTokens} tokens</span>
              )}
            </>
          )
        )}
      </div>
    </div>
  );
});
