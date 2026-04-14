import { useState, useCallback, useMemo, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useCodeSession } from '../../hooks/useCodeSession';
import { AnimatedBackground } from '../Home/AnimatedBackground';
import { PageShell } from '../ui';
import { MessageList } from './MessageList';
import { InputArea } from './InputArea';
import { SessionHeader } from './SessionHeader';
import { StatusBar } from './StatusBar';
import { ChatSessionList, addCustomFolder } from './SessionList';
import { WorkingDirPicker } from './WorkingDirPicker';
import { ModelPicker } from './ModelPicker';
import type { SlashCommand } from '../../hooks/useSlashCommands';
import styles from './CodeSession.module.css';

interface CodeSessionProps {
  sidebarOpen?: boolean;
}

export function CodeSession({ sidebarOpen = false }: CodeSessionProps) {
  const { sessionId: urlSessionId } = useParams<{ sessionId?: string }>();
  const navigate = useNavigate();
  const isSessionRoute = !!urlSessionId;

  const {
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
  } = useCodeSession();

  const [showDirPicker, setShowDirPicker] = useState(false);
  const [showModelPicker, setShowModelPicker] = useState(false);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const [dirPickerMode, setDirPickerMode] = useState<'session' | 'workspace'>('session');
  const [listRefreshKey, setListRefreshKey] = useState(0);

  // When URL has sessionId but no active session, resume it
  useEffect(() => {
    if (urlSessionId && (!activeSession || activeSession.id !== urlSessionId)) {
      resumeSession(urlSessionId);
    }
  }, [urlSessionId, activeSession, resumeSession]);

  // Track whether we're expecting a redirect (from Home prompt or explicit create)
  const [pendingRedirect, setPendingRedirect] = useState(false);

  // When a session is created and we're expecting a redirect, update URL.
  // Also bump listRefreshKey so the session list refetches next time we
  // land on /chat — this surfaces the new session without a full reload,
  // and picks up any sub-agent sessions the backend may have written.
  useEffect(() => {
    if (activeSession && pendingRedirect) {
      setPendingRedirect(false);
      setListRefreshKey(k => k + 1);
      navigate(`/chat/${activeSession.id}`, { replace: true });
    }
  }, [activeSession, pendingRedirect, navigate]);

  // Auto-create session from Home prompt (pending cwd in localStorage).
  // Uses localStorage because Safari PWA can wipe sessionStorage on
  // relaunch — read-and-remove keeps it single-shot.
  useEffect(() => {
    if (!isSessionRoute && connected && backendInfo) {
      const pendingCwd = localStorage.getItem('adjutant-pending-cwd');
      if (pendingCwd) {
        localStorage.removeItem('adjutant-pending-cwd');
        const model = backendInfo.models.expensive;
        setPendingRedirect(true);
        createSession(pendingCwd, model);
      }
    }
  }, [isSessionRoute, connected, backendInfo, createSession]);

  // Pick up pending message from Home prompt after session is active
  useEffect(() => {
    if (activeSession && connected) {
      const pending = localStorage.getItem('adjutant-pending-message');
      if (pending) {
        localStorage.removeItem('adjutant-pending-message');
        setTimeout(() => sendChatMessage(pending), 300);
      }
    }
  }, [activeSession, connected, sendChatMessage]);

  const handleNewSession = useCallback(() => {
    setDirPickerMode('session');
    setShowDirPicker(true);
  }, []);

  const handleAddWorkspace = useCallback(() => {
    setDirPickerMode('workspace');
    setShowDirPicker(true);
  }, []);

  const handleQuickNewSession = useCallback((cwd: string) => {
    const model = selectedModel || backendInfo?.models.expensive;
    setPendingRedirect(true);
    createSession(cwd, model || undefined);
  }, [createSession, selectedModel, backendInfo]);

  const handleDirSelect = useCallback((path: string) => {
    setShowDirPicker(false);
    if (dirPickerMode === 'workspace') {
      addCustomFolder(path);
      setListRefreshKey(k => k + 1);
    } else {
      const model = selectedModel || backendInfo?.models.expensive;
      setPendingRedirect(true);
      createSession(path, model || undefined);
    }
  }, [dirPickerMode, createSession, selectedModel, backendInfo]);

  const handleResume = useCallback((sessionId: string) => {
    navigate(`/chat/${sessionId}`);
  }, [navigate]);

  const handleResumeCliSession = useCallback((cliSessionId: string, cwd: string) => {
    const model = selectedModel || backendInfo?.models.expensive;
    setPendingRedirect(true);
    createSession(cwd, model || undefined, cliSessionId);
  }, [createSession, selectedModel, backendInfo]);

  const handleBack = useCallback(() => {
    endSession();
    navigate('/chat');
  }, [endSession, navigate]);

  const addSystemMessage = useCallback((text: string) => {
    setMessages(prev => [...prev, {
      id: crypto.randomUUID(),
      role: 'system' as const,
      content: text,
      timestamp: new Date().toISOString(),
    }]);
  }, [setMessages]);

  const handleSlashCommand = useCallback((cmd: SlashCommand) => {
    switch (cmd.action) {
      case 'new':
        handleNewSession();
        break;
      case 'sessions':
        navigate('/chat');
        break;
      case 'browse':
        setShowDirPicker(true);
        break;
      case 'model':
        setShowModelPicker(true);
        break;
      case 'cost': {
        const cost = activeSession?.totalCostUsd;
        if (cost != null && cost > 0) {
          addSystemMessage(`Session cost: $${cost.toFixed(4)}`);
        } else {
          addSystemMessage('No cost data available for this session.');
        }
        break;
      }
      case 'help':
        addSystemMessage(
          'Available commands:\n' +
          '/new — Start a new session\n' +
          '/sessions — View past sessions\n' +
          '/browse — Change working directory\n' +
          '/model — Switch model tier\n' +
          '/cost — Show session cost summary\n' +
          '/help — Show this help'
        );
        break;
    }
  }, [activeSession, handleNewSession, addSystemMessage, navigate]);

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.key === 'l') {
        e.preventDefault();
        clearMessages();
      }
      if (e.ctrlKey && e.key === 'c' && isStreaming) {
        e.preventDefault();
        cancelMessage();
      }
      if (e.ctrlKey && e.key === 'n') {
        e.preventDefault();
        handleNewSession();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [clearMessages, cancelMessage, isStreaming, handleNewSession]);

  const lastUserMessage = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'user') return messages[i].content;
    }
    return undefined;
  }, [messages]);

  const rootClass = `${styles.root} ${sidebarOpen ? styles.sidebarOpen : ''}`;

  // --- Session list view (/chat) ---
  if (!isSessionRoute) {
    return (
      <PageShell sidebarOpen={sidebarOpen} background={<AnimatedBackground />}>
        <nav className={styles.topNav}>
          <h1 className={styles.pageTitle}>Chat</h1>
          <div className={styles.topNavActions}>
            <button className={styles.newSessionBtn} onClick={handleAddWorkspace} disabled={!connected}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>
                <line x1="12" y1="11" x2="12" y2="17"/>
                <line x1="9" y1="14" x2="15" y2="14"/>
              </svg>
              Add workspace
            </button>
          </div>
        </nav>

        {backendError ? (
          <div className={styles.backendError}>
            <h2>No CLI Backend Found</h2>
            <p>{backendError}</p>
            <p>Install Claude Code (<code>npm i -g @anthropic-ai/claude-code</code>) or OpenCode, then configure <code>llm.backend</code> in adjutant.yaml.</p>
          </div>
        ) : (
          <ChatSessionList
            key={listRefreshKey}
            onResume={handleResume}
            onResumeCliSession={handleResumeCliSession}
            onNewSession={handleQuickNewSession}
          />
        )}

        <WorkingDirPicker
          open={showDirPicker}
          onSelect={handleDirSelect}
          onClose={() => setShowDirPicker(false)}
        />
      </PageShell>
    );
  }

  // --- Active session view (/chat/:sessionId) ---
  return (
    <div className={rootClass}>
      <AnimatedBackground />

      {/* Connection banner */}
      {!connected && (
        <div className={styles.connectionBanner}>
          {reconnecting ? 'Connection lost. Reconnecting...' : 'Disconnected'}
        </div>
      )}

      {/* Error banner */}
      {error && (
        <div className={styles.errorBanner}>
          <span>{error}</span>
          <button className={styles.errorDismiss} onClick={() => {}}>x</button>
        </div>
      )}

      <div className={styles.chatContent}>
        <SessionHeader
          session={activeSession}
          backendInfo={backendInfo}
          onNewSession={handleNewSession}
          onBack={handleBack}
        />
        <MessageList
          messages={messages}
          streamingContent={streamingContent}
          isStreaming={isStreaming}
        />
        <InputArea
          onSend={sendChatMessage}
          onCancel={cancelMessage}
          onSlashCommand={handleSlashCommand}
          isStreaming={isStreaming}
          disabled={!connected}
          lastUserMessage={lastUserMessage}
        />
        {activeSession && (
          <StatusBar
            cwd={activeSession.cwd}
            backendName={backendInfo?.name || null}
            connected={connected}
            reconnecting={reconnecting}
          />
        )}
      </div>

      {/* Modals */}
      <WorkingDirPicker
        open={showDirPicker}
        onSelect={handleDirSelect}
        onClose={() => setShowDirPicker(false)}
      />
      {backendInfo && (
        <ModelPicker
          open={showModelPicker}
          backendInfo={backendInfo}
          currentModel={selectedModel || activeSession?.model || backendInfo.models.expensive}
          onSelect={setSelectedModel}
          onClose={() => setShowModelPicker(false)}
        />
      )}
    </div>
  );
}

export default CodeSession;
