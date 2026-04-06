import { useState, useCallback, useMemo, useEffect } from 'react';
import { useCodeSession } from '../../hooks/useCodeSession';
import { MessageList } from './MessageList';
import { InputArea } from './InputArea';
import { SessionHeader } from './SessionHeader';
import { StatusBar } from './StatusBar';
import { SessionList, RecentSessions } from './SessionList';
import { WorkingDirPicker } from './WorkingDirPicker';
import { ModelPicker } from './ModelPicker';
import type { SlashCommand } from '../../hooks/useSlashCommands';
import styles from './CodeSession.module.css';

interface CodeSessionProps {
  sidebarOpen?: boolean;
}

export function CodeSession({ sidebarOpen = false }: CodeSessionProps) {
  const {
    connected,
    reconnecting,
    backendInfo,
    backendError,
    activeSession,
    messages,
    streamingContent,
    isStreaming,
    error,
    createSession,
    resumeSession,
    sendChatMessage,
    cancelMessage,
    clearMessages,
  } = useCodeSession();

  const [showDirPicker, setShowDirPicker] = useState(false);
  const [showSessionList, setShowSessionList] = useState(false);
  const [showModelPicker, setShowModelPicker] = useState(false);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const [isResumed, setIsResumed] = useState(false);

  const handleNewSession = useCallback(() => {
    setShowDirPicker(true);
  }, []);

  const handleDirSelect = useCallback((path: string) => {
    setShowDirPicker(false);
    setIsResumed(false);
    const model = selectedModel || backendInfo?.models.expensive;
    createSession(path, model || undefined);
  }, [createSession, selectedModel, backendInfo]);

  const handleResume = useCallback((sessionId: string) => {
    setIsResumed(true);
    resumeSession(sessionId);
  }, [resumeSession]);

  const addSystemMessage = useCallback((text: string) => {
    setMessages(prev => [...prev, {
      id: crypto.randomUUID(),
      role: 'system' as const,
      content: text,
      timestamp: new Date().toISOString(),
    }]);
  }, []);

  const handleSlashCommand = useCallback((cmd: SlashCommand) => {
    switch (cmd.action) {
      case 'new':
        handleNewSession();
        break;
      case 'sessions':
        setShowSessionList(true);
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
  }, [activeSession, handleNewSession, addSystemMessage]);

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Ctrl+L: clear messages
      if (e.ctrlKey && e.key === 'l') {
        e.preventDefault();
        clearMessages();
      }
      // Ctrl+C while streaming: cancel
      if (e.ctrlKey && e.key === 'c' && isStreaming) {
        e.preventDefault();
        cancelMessage();
      }
      // Ctrl+N: new session
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

  return (
    <div className={`${styles.root} ${sidebarOpen ? styles.sidebarOpen : ''}`}>
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

      {/* Content area — max-width centered like Dashboard */}
      <div className={styles.content}>
        {/* Backend not found state */}
        {backendError ? (
          <div className={styles.backendError}>
            <h2>No CLI Backend Found</h2>
            <p>{backendError}</p>
            <p>Install Claude Code (<code>npm i -g @anthropic-ai/claude-code</code>) or OpenCode, then configure <code>llm.backend</code> in adjutant.yaml.</p>
          </div>
        ) : !activeSession ? (
          /* No active session — show start screen with recent sessions */
          <div className={styles.noSession}>
            <h2>Code Session</h2>
            <p>Interactive coding assistant powered by {backendInfo?.name || 'CLI'}</p>
            <button className={styles.startBtn} onClick={handleNewSession} disabled={!connected}>
              Start New Session
            </button>
            <RecentSessions
              onResume={handleResume}
              onShowAll={() => setShowSessionList(true)}
            />
          </div>
        ) : (
          /* Active session — show chat */
          <>
            <SessionHeader
              session={activeSession}
              backendInfo={backendInfo}
              isResumed={isResumed}
              onNewSession={handleNewSession}
              onShowSessions={() => setShowSessionList(true)}
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
            <StatusBar
              cwd={activeSession.cwd}
              backendName={backendInfo?.name || null}
              connected={connected}
              reconnecting={reconnecting}
            />
          </>
        )}
      </div>

      {/* Modals */}
      <WorkingDirPicker
        open={showDirPicker}
        onSelect={handleDirSelect}
        onClose={() => setShowDirPicker(false)}
      />
      <SessionList
        open={showSessionList}
        onResume={handleResume}
        onClose={() => setShowSessionList(false)}
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
