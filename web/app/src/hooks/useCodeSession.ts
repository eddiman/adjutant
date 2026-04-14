/**
 * WebSocket hook for code session communication.
 *
 * Manages connection lifecycle with exponential backoff reconnection,
 * streaming text accumulation, and session state.
 *
 * IMPORTANT: The WS message handler uses a ref-based pattern to avoid
 * recreating the WebSocket connection when React state changes. The
 * handler ref is updated on every render, but the actual ws.onmessage
 * callback is stable (reads from the ref).
 */

import { useState, useEffect, useRef, useCallback } from 'react';

// Types mirrored from API (no cross-package imports)
export interface CliBackendInfo {
  name: 'claude-cli' | 'opencode';
  binary: string;
  permissionMode: string;
  models: { cheap: string; medium: string; expensive: string };
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  model?: string;
  durationMs?: number;
  costUsd?: number | null;
  inputTokens?: number;
  outputTokens?: number;
  error?: string;
}

export interface SessionInfo {
  id: string;
  name: string;
  cliSessionId: string | null;
  backend: 'claude-cli' | 'opencode';
  cwd: string;
  model: string;
  messages: ChatMessage[];
  createdAt: string;
  lastActiveAt: string;
  totalCostUsd: number | null;
}

interface WsServerMessage {
  type: string;
  session?: SessionInfo;
  sessions?: SessionInfo[];
  sessionId?: string;
  content?: string;
  message?: ChatMessage;
  sessionName?: string;
  error?: string;
  code?: string;
  backend?: CliBackendInfo;
}

export function useCodeSession() {
  const [connected, setConnected] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);
  const [backendInfo, setBackendInfo] = useState<CliBackendInfo | null>(null);
  const [backendError, setBackendError] = useState<string | null>(null);
  const [activeSession, setActiveSession] = useState<SessionInfo | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streamingContent, setStreamingContent] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const reconnectAttemptRef = useRef(0);
  const mountedRef = useRef(true);
  const autoResumeAttemptedRef = useRef(false);
  // Ref to track streaming content for the error handler without
  // causing handleMessage to depend on streamingContent state
  const streamingContentRef = useRef('');

  // Keep ref in sync with state
  useEffect(() => {
    streamingContentRef.current = streamingContent;
  }, [streamingContent]);

  // Stable message handler — uses refs, no state dependencies.
  // This prevents WS reconnection on every state change.
  const handleMessageRef = useRef<((event: MessageEvent) => void) | undefined>(undefined);
  handleMessageRef.current = (event: MessageEvent) => {
    let msg: WsServerMessage;
    try {
      msg = JSON.parse(event.data);
    } catch {
      return;
    }

    switch (msg.type) {
      case 'backend.info':
        if (msg.backend) {
          setBackendInfo(msg.backend);
          setBackendError(null);
        }
        break;

      case 'session.created':
      case 'session.resumed':
        if (msg.session) {
          setActiveSession(msg.session);
          setMessages(msg.session.messages || []);
          setError(null);
          try { localStorage.setItem('adjutant-code-session-id', msg.session.id); } catch { /* ignore */ }
        }
        break;

      case 'message.delta':
        setStreamingContent(prev => prev + (msg.content || ''));
        break;

      case 'message.complete':
        if (msg.message) {
          setMessages(prev => [...prev, msg.message!]);
          setStreamingContent('');
          setIsStreaming(false);
          setActiveSession(prev => {
            if (!prev) return prev;
            const updates: Partial<SessionInfo> = {};
            if (msg.message!.costUsd != null) {
              updates.totalCostUsd = (prev.totalCostUsd || 0) + (msg.message!.costUsd || 0);
            }
            if (msg.sessionName && msg.sessionName !== prev.name) {
              updates.name = msg.sessionName;
            }
            return Object.keys(updates).length ? { ...prev, ...updates } : prev;
          });
        }
        break;

      case 'message.error':
        setIsStreaming(false);
        if (msg.code !== 'CANCELLED') {
          setError(msg.error || 'Unknown error');
          // Use ref to read current streaming content without dependency
          const currentStreaming = streamingContentRef.current;
          if (currentStreaming) {
            setMessages(prev => [...prev, {
              id: crypto.randomUUID(),
              role: 'assistant',
              content: currentStreaming,
              timestamp: new Date().toISOString(),
              error: msg.error,
            }]);
            setStreamingContent('');
          }
        } else {
          setStreamingContent('');
        }
        break;

      case 'error':
        if (msg.code === 'BACKEND_NOT_FOUND') {
          setBackendError(msg.error || 'Backend not found');
        } else if (msg.code === 'SESSION_NOT_FOUND') {
          try { localStorage.removeItem('adjutant-code-session-id'); } catch { /* ignore */ }
        } else {
          setError(msg.error || 'Unknown error');
        }
        break;
    }
  };

  // Stable onmessage callback that delegates to the ref
  const stableOnMessage = useCallback((event: MessageEvent) => {
    handleMessageRef.current?.(event);
  }, []);

  // Single stable connect function — no dependencies that change
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN ||
        wsRef.current?.readyState === WebSocket.CONNECTING) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${window.location.host}/ws/code-session`;
    const ws = new WebSocket(url);

    ws.onopen = () => {
      if (!mountedRef.current) return;
      setConnected(true);
      setReconnecting(false);
      reconnectAttemptRef.current = 0;

      // Mark first connect done (auto-resume removed — routes drive session loading now)
      autoResumeAttemptedRef.current = true;
    };

    ws.onclose = () => {
      if (!mountedRef.current) return;
      setConnected(false);
      wsRef.current = null;

      const delay = Math.min(1000 * Math.pow(2, reconnectAttemptRef.current), 30000);
      reconnectAttemptRef.current++;
      setReconnecting(true);

      reconnectTimeoutRef.current = setTimeout(() => {
        if (mountedRef.current) connect();
      }, delay);
    };

    ws.onerror = () => {
      // onclose will fire after this
    };

    ws.onmessage = stableOnMessage;
    wsRef.current = ws;
  }, [stableOnMessage]);

  useEffect(() => {
    mountedRef.current = true;
    connect();

    return () => {
      mountedRef.current = false;
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  // Force reconnect when the tab/PWA becomes visible or comes back online.
  // iOS Safari PWA suspension does not reliably fire `ws.onclose`, so the
  // exponential-backoff reconnect path alone isn't enough — on wake we
  // actively clear any pending timeout, reset the backoff counter, and
  // call connect() if the socket isn't already OPEN.
  useEffect(() => {
    const tryReconnect = () => {
      if (!mountedRef.current) return;
      if (document.visibilityState === 'hidden') return;
      const ws = wsRef.current;
      if (ws && ws.readyState === WebSocket.OPEN) return;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = undefined;
      }
      reconnectAttemptRef.current = 0;
      // If there is a stale socket still in CONNECTING/CLOSING, close it
      // so connect() can create a fresh one.
      if (ws && ws.readyState !== WebSocket.CLOSED) {
        try { ws.onclose = null; ws.close(); } catch { /* ignore */ }
        wsRef.current = null;
      }
      connect();
    };

    window.addEventListener('visibilitychange', tryReconnect);
    window.addEventListener('focus', tryReconnect);
    window.addEventListener('online', tryReconnect);
    return () => {
      window.removeEventListener('visibilitychange', tryReconnect);
      window.removeEventListener('focus', tryReconnect);
      window.removeEventListener('online', tryReconnect);
    };
  }, [connect]);

  const sendWs = useCallback((data: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  const createSession = useCallback((cwd: string, model?: string, cliSessionId?: string) => {
    // Clear any previous session so the pendingRedirect effect in CodeSession.tsx
    // waits for the NEW session.created payload instead of navigating to the
    // stale activeSession left over from a previous /chat/:id visit.
    setActiveSession(null);
    setMessages([]);
    setStreamingContent('');
    setError(null);
    sendWs({ type: 'session.create', cwd, model, cliSessionId });
  }, [sendWs]);

  const resumeSession = useCallback((sessionId: string) => {
    setStreamingContent('');
    setError(null);
    sendWs({ type: 'session.resume', sessionId });
  }, [sendWs]);

  const sendChatMessage = useCallback((content: string) => {
    if (!activeSession) return;

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content,
      timestamp: new Date().toISOString(),
    };
    setMessages(prev => [...prev, userMsg]);
    setStreamingContent('');
    setIsStreaming(true);
    setError(null);

    sendWs({ type: 'message.send', sessionId: activeSession.id, content });
  }, [activeSession, sendWs]);

  const cancelMessage = useCallback(() => {
    if (!activeSession) return;
    sendWs({ type: 'message.cancel', sessionId: activeSession.id });
  }, [activeSession, sendWs]);

  const clearMessages = useCallback(() => {
    setMessages([]);
    setStreamingContent('');
    setError(null);
  }, []);

  const endSession = useCallback(() => {
    setActiveSession(null);
    setMessages([]);
    setStreamingContent('');
    setError(null);
    try { localStorage.removeItem('adjutant-code-session-id'); } catch { /* ignore */ }
  }, []);

  return {
    connected,
    reconnecting,
    backendInfo,
    backendError,
    activeSession,
    messages,
    setMessages,
    streamingContent,
    isStreaming,
    error,
    createSession,
    resumeSession,
    sendChatMessage,
    cancelMessage,
    clearMessages,
    endSession,
  };
}
