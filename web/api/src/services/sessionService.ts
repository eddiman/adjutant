/**
 * In-memory session store for code sessions.
 *
 * Sessions are transient — lost on server restart. The CLI itself maintains
 * session history on disk (Claude CLI: ~/.claude/sessions/, OpenCode: its state dir).
 * On resume, the CLI re-reads its own history via --resume/--session flags.
 *
 * Concurrency capped at MAX_CONCURRENT active processes.
 */

import { randomUUID } from 'crypto';
import type { CodeSession, ChatMessage, CliBackendName, CompleteEvent } from '../types/session.js';
import type { RunHandle } from './cliAdapter.js';

const MAX_CONCURRENT = 3;

class SessionService {
  private sessions = new Map<string, CodeSession>();
  private activeHandles = new Map<string, RunHandle>();

  create(backend: CliBackendName, cwd: string, model: string): CodeSession {
    const session: CodeSession = {
      id: randomUUID(),
      name: 'New session',
      cliSessionId: null,
      backend,
      cwd,
      model,
      messages: [],
      createdAt: new Date().toISOString(),
      lastActiveAt: new Date().toISOString(),
      totalCostUsd: null,
    };
    this.sessions.set(session.id, session);
    return session;
  }

  get(id: string): CodeSession | undefined {
    return this.sessions.get(id);
  }

  list(): CodeSession[] {
    return Array.from(this.sessions.values()).sort(
      (a, b) => new Date(b.lastActiveAt).getTime() - new Date(a.lastActiveAt).getTime(),
    );
  }

  delete(id: string): boolean {
    this.cancelHandle(id);
    return this.sessions.delete(id);
  }

  addMessage(sessionId: string, message: ChatMessage): void {
    const session = this.sessions.get(sessionId);
    if (!session) return;
    session.messages.push(message);
    session.lastActiveAt = new Date().toISOString();

    // Auto-name from first user message
    if (message.role === 'user' && session.name === 'New session') {
      session.name = message.content.slice(0, 60).replace(/\n/g, ' ').trim();
      if (message.content.length > 60) session.name += '...';
    }
  }

  updateFromComplete(sessionId: string, event: CompleteEvent): void {
    const session = this.sessions.get(sessionId);
    if (!session) return;

    if (event.cliSessionId && !session.cliSessionId) {
      session.cliSessionId = event.cliSessionId;
    }

    if (event.costUsd != null) {
      session.totalCostUsd = (session.totalCostUsd || 0) + event.costUsd;
    }
  }

  // === Active handle tracking ===

  canStartProcess(): boolean {
    return this.activeHandles.size < MAX_CONCURRENT;
  }

  getActiveCount(): number {
    return this.activeHandles.size;
  }

  setHandle(sessionId: string, handle: RunHandle): void {
    this.activeHandles.set(sessionId, handle);
  }

  removeHandle(sessionId: string): void {
    this.activeHandles.delete(sessionId);
  }

  cancelHandle(sessionId: string): void {
    const handle = this.activeHandles.get(sessionId);
    if (handle) {
      handle.cancel();
      this.activeHandles.delete(sessionId);
    }
  }

  cancelAllHandles(): void {
    for (const [id, handle] of this.activeHandles) {
      handle.cancel();
      this.activeHandles.delete(id);
    }
  }

  getHandle(sessionId: string): RunHandle | undefined {
    return this.activeHandles.get(sessionId);
  }
}

export const sessionService = new SessionService();
