import { z } from 'zod';

// === CLI Backend Detection ===

export type CliBackendName = 'claude-cli' | 'opencode';

export interface CliBackendInfo {
  name: CliBackendName;
  binary: string;
  permissionMode: string;
  models: {
    cheap: string;
    medium: string;
    expensive: string;
  };
}

// === Session ===

export interface CodeSession {
  id: string;
  name: string;
  cliSessionId: string | null;
  backend: CliBackendName;
  cwd: string;
  model: string;
  messages: ChatMessage[];
  createdAt: string;
  lastActiveAt: string;
  totalCostUsd: number | null;
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

// === WebSocket Protocol ===

// Client -> Server
export const WsClientMessageSchema = z.discriminatedUnion('type', [
  z.object({ type: z.literal('session.create'), cwd: z.string(), model: z.string().optional() }),
  z.object({ type: z.literal('session.resume'), sessionId: z.string() }),
  z.object({ type: z.literal('session.list') }),
  z.object({ type: z.literal('message.send'), sessionId: z.string(), content: z.string() }),
  z.object({ type: z.literal('message.cancel'), sessionId: z.string() }),
]);

export type WsClientMessage = z.infer<typeof WsClientMessageSchema>;

// Server -> Client
export type WsServerMessage =
  | { type: 'session.created'; session: CodeSession }
  | { type: 'session.resumed'; session: CodeSession }
  | { type: 'session.list'; sessions: CodeSession[] }
  | { type: 'message.delta'; sessionId: string; content: string }
  | { type: 'message.complete'; sessionId: string; message: ChatMessage; sessionName?: string }
  | { type: 'message.error'; sessionId: string; error: string; code?: string }
  | { type: 'backend.info'; backend: CliBackendInfo }
  | { type: 'error'; error: string; code?: string };

// === Normalized Stream Event (internal, from CLI adapters) ===

export interface CompleteEvent {
  cliSessionId: string | null;
  model?: string;
  costUsd?: number | null;
  inputTokens?: number;
  outputTokens?: number;
  durationMs?: number;
}

export interface ErrorEvent {
  message: string;
  code?: string;
}
