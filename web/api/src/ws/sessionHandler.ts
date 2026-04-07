/**
 * WebSocket message handler for code sessions.
 *
 * Routes incoming WS messages to sessionService and cliAdapter.
 * Streams CLI output back to the client as message.delta events.
 * Cleans up all active processes when the WebSocket disconnects.
 */

import type { WebSocket } from 'ws';
import { randomUUID } from 'crypto';
import { backendDetector } from '../services/backendDetector.js';
import { sessionService } from '../services/sessionService.js';
import { runCli } from '../services/cliAdapter.js';
import { WsClientMessageSchema } from '../types/session.js';
import type { WsServerMessage, ChatMessage, CompleteEvent, ErrorEvent } from '../types/session.js';

function send(ws: WebSocket, msg: WsServerMessage): void {
  if (ws.readyState === ws.OPEN) {
    ws.send(JSON.stringify(msg));
  }
}

export function handleConnection(ws: WebSocket): void {
  // Track which sessions this connection is actively running
  const connectionSessionIds = new Set<string>();

  // Send backend info on connect
  (async () => {
    const backend = await backendDetector.detect();
    if (backend) {
      send(ws, { type: 'backend.info', backend });
    } else {
      send(ws, {
        type: 'error',
        error: 'No CLI backend found. Configure llm.backend in adjutant.yaml and ensure the CLI binary is installed.',
        code: 'BACKEND_NOT_FOUND',
      });
    }
  })();

  ws.on('message', async (data) => {
    let raw: unknown;
    try {
      raw = JSON.parse(data.toString());
    } catch {
      send(ws, { type: 'error', error: 'Invalid JSON' });
      return;
    }

    const parsed = WsClientMessageSchema.safeParse(raw);
    if (!parsed.success) {
      send(ws, { type: 'error', error: `Invalid message: ${parsed.error.message}` });
      return;
    }

    const msg = parsed.data;

    switch (msg.type) {
      case 'session.create': {
        const backend = await backendDetector.detect();
        if (!backend) {
          send(ws, { type: 'error', error: 'Backend not available', code: 'BACKEND_NOT_FOUND' });
          return;
        }

        const model = msg.model || backend.models.expensive;
        const session = sessionService.create(backend.name, msg.cwd, model);
        // If resuming a CLI session, pre-set the CLI session ID for --resume
        if (msg.cliSessionId) {
          session.cliSessionId = msg.cliSessionId;
        }
        connectionSessionIds.add(session.id);
        send(ws, { type: 'session.created', session });
        break;
      }

      case 'session.resume': {
        const session = sessionService.get(msg.sessionId);
        if (!session) {
          send(ws, { type: 'error', error: 'Session not found', code: 'SESSION_NOT_FOUND' });
          return;
        }
        connectionSessionIds.add(session.id);
        send(ws, { type: 'session.resumed', session });
        break;
      }

      case 'session.list': {
        send(ws, { type: 'session.list', sessions: sessionService.list() });
        break;
      }

      case 'message.send': {
        const session = sessionService.get(msg.sessionId);
        if (!session) {
          send(ws, { type: 'message.error', sessionId: msg.sessionId, error: 'Session not found' });
          return;
        }

        const backend = await backendDetector.detect();
        if (!backend) {
          send(ws, { type: 'message.error', sessionId: msg.sessionId, error: 'Backend not available', code: 'BACKEND_NOT_FOUND' });
          return;
        }

        if (!sessionService.canStartProcess()) {
          send(ws, {
            type: 'message.error',
            sessionId: msg.sessionId,
            error: `Too many concurrent sessions (max ${sessionService.getActiveCount()})`,
            code: 'CONCURRENCY_LIMIT',
          });
          return;
        }

        // Add user message
        const userMessage: ChatMessage = {
          id: randomUUID(),
          role: 'user',
          content: msg.content,
          timestamp: new Date().toISOString(),
        };
        sessionService.addMessage(msg.sessionId, userMessage);

        const startTime = Date.now();
        let accumulatedContent = '';

        const handle = runCli({
          backend,
          prompt: msg.content,
          cwd: session.cwd,
          model: session.model,
          cliSessionId: session.cliSessionId || undefined,
          onDelta: (text: string) => {
            accumulatedContent += text;
            send(ws, { type: 'message.delta', sessionId: msg.sessionId, content: text });
          },
          onComplete: (event: CompleteEvent) => {
            sessionService.removeHandle(msg.sessionId);
            sessionService.updateFromComplete(msg.sessionId, event);

            const assistantMessage: ChatMessage = {
              id: randomUUID(),
              role: 'assistant',
              content: accumulatedContent,
              timestamp: new Date().toISOString(),
              model: session.model,
              durationMs: event.durationMs || (Date.now() - startTime),
              costUsd: event.costUsd,
              inputTokens: event.inputTokens,
              outputTokens: event.outputTokens,
            };
            sessionService.addMessage(msg.sessionId, assistantMessage);

            const updatedSession = sessionService.get(msg.sessionId);
            send(ws, { type: 'message.complete', sessionId: msg.sessionId, message: assistantMessage, sessionName: updatedSession?.name });
          },
          onError: (event: ErrorEvent) => {
            sessionService.removeHandle(msg.sessionId);

            const errorMessage: ChatMessage = {
              id: randomUUID(),
              role: 'assistant',
              content: accumulatedContent || '',
              timestamp: new Date().toISOString(),
              error: event.message,
              durationMs: Date.now() - startTime,
            };
            sessionService.addMessage(msg.sessionId, errorMessage);

            send(ws, {
              type: 'message.error',
              sessionId: msg.sessionId,
              error: event.message,
              code: event.code,
            });
          },
        });

        sessionService.setHandle(msg.sessionId, handle);
        break;
      }

      case 'message.cancel': {
        sessionService.cancelHandle(msg.sessionId);
        send(ws, {
          type: 'message.error',
          sessionId: msg.sessionId,
          error: 'Message cancelled',
          code: 'CANCELLED',
        });
        break;
      }
    }
  });

  ws.on('close', () => {
    // Cancel all active processes for this connection
    for (const sessionId of connectionSessionIds) {
      sessionService.cancelHandle(sessionId);
    }
    connectionSessionIds.clear();
  });

  ws.on('error', (err) => {
    console.error('[ws] Connection error:', err.message);
    for (const sessionId of connectionSessionIds) {
      sessionService.cancelHandle(sessionId);
    }
    connectionSessionIds.clear();
  });
}
