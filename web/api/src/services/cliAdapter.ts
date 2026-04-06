/**
 * CLI Adapter — spawns Claude CLI or OpenCode subprocesses and streams responses.
 *
 * Handles two completely different NDJSON formats:
 * - Claude CLI (stream-json): content_block_delta events with text_delta
 * - OpenCode (--format json): type:"text" events with part.text
 *
 * Includes stream-json → json fallback for Claude CLI if stream-json is
 * not supported (per backend-migration-log.md:51).
 *
 * Process lifecycle: spawn → readline stdout → cancel via SIGINT cascade →
 * orphan cleanup for OpenCode language servers.
 */

import { spawn, execSync, type ChildProcess } from 'child_process';
import { createInterface } from 'readline';
import type { CliBackendInfo, CompleteEvent, ErrorEvent } from '../types/session.js';

// Claude CLI model alias map (matches backend_claude_cli.py:27-35)
const CLAUDE_ALIASES: Record<string, string> = {
  'anthropic/claude-haiku-4-5': 'haiku',
  'anthropic/claude-sonnet-4-6': 'sonnet',
  'anthropic/claude-opus-4-6': 'opus',
};

const DEFAULT_ALLOWED_TOOLS = 'Read,Glob,Grep,Edit,Write,Bash(*)';
const MESSAGE_TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes

// Track whether stream-json is supported (auto-detected on first use)
let claudeStreamJsonSupported = true;

export interface RunHandle {
  cancel(): void;
  promise: Promise<void>;
}

export interface RunParams {
  backend: CliBackendInfo;
  prompt: string;
  cwd: string;
  model?: string;
  cliSessionId?: string;
  onDelta: (text: string) => void;
  onComplete: (event: CompleteEvent) => void;
  onError: (event: ErrorEvent) => void;
}

// === OpenCode orphan cleanup ===

function getLanguageServerPids(): Set<number> {
  const pids = new Set<number>();
  try {
    const output = execSync(
      'pgrep -f "bash-language-server|yaml-language-server"',
      { encoding: 'utf-8', timeout: 3000 },
    );
    for (const line of output.trim().split('\n')) {
      const pid = parseInt(line.trim(), 10);
      if (!isNaN(pid)) pids.add(pid);
    }
  } catch {
    // pgrep returns non-zero if no matches
  }
  return pids;
}

function killOrphanPids(before: Set<number>, after: Set<number>): void {
  const newPids = new Set([...after].filter(p => !before.has(p)));
  if (newPids.size === 0) return;

  for (const pid of newPids) {
    try { process.kill(pid, 'SIGTERM'); } catch { /* already gone */ }
  }

  setTimeout(() => {
    for (const pid of newPids) {
      try { process.kill(pid, 'SIGKILL'); } catch { /* already gone */ }
    }
  }, 1000);
}

// === Cancel helper ===

function cancelProcess(proc: ChildProcess): void {
  if (proc.exitCode !== null || proc.killed) return;

  try { proc.kill('SIGINT'); } catch { /* ignore */ }

  setTimeout(() => {
    if (proc.exitCode !== null || proc.killed) return;
    try { proc.kill('SIGTERM'); } catch { /* ignore */ }

    setTimeout(() => {
      if (proc.exitCode !== null || proc.killed) return;
      try { proc.kill('SIGKILL'); } catch { /* ignore */ }
    }, 2000);
  }, 2000);
}

// === Claude CLI ===

function buildClaudeArgs(params: RunParams, useStreamJson: boolean): string[] {
  const { backend, prompt, model, cliSessionId } = params;
  const args = ['-p', '--output-format', useStreamJson ? 'stream-json' : 'json'];

  // stream-json requires --verbose when used with -p
  if (useStreamJson) {
    args.push('--verbose');
  }

  if (model) {
    const alias = CLAUDE_ALIASES[model] || model;
    args.push('--model', alias);
  }

  // Permission mode
  if (backend.permissionMode === 'allowlist') {
    args.push('--allowedTools', DEFAULT_ALLOWED_TOOLS);
  } else {
    args.push('--dangerously-skip-permissions');
  }

  if (cliSessionId) {
    args.push('--resume', cliSessionId);
  }

  args.push(prompt);
  return args;
}

function runClaudeStreaming(params: RunParams): RunHandle {
  const { backend, cwd, onDelta, onComplete, onError } = params;
  const args = buildClaudeArgs(params, true);

  let cancelled = false;
  const proc = spawn(backend.binary, args, {
    cwd,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env },
  });

  let cliSessionId: string | null = null;
  let costUsd: number | null = null;
  let inputTokens: number | undefined;
  let outputTokens: number | undefined;
  let durationMs: number | undefined;
  let gotResult = false;
  let gotDelta = false;
  let completeCalled = false;
  let stderrBuf = '';

  const rl = createInterface({ input: proc.stdout! });

  rl.on('line', (line: string) => {
    if (cancelled) return;
    const trimmed = line.trim();
    if (!trimmed) return;

    let record: Record<string, unknown>;
    try {
      record = JSON.parse(trimmed);
    } catch {
      return; // Skip malformed lines
    }

    const type = record.type as string;

    // Standard Anthropic API streaming events
    if (type === 'content_block_delta') {
      const delta = record.delta as Record<string, unknown> | undefined;
      if (delta?.type === 'text_delta' && typeof delta.text === 'string') {
        gotDelta = true;
        onDelta(delta.text);
      }
    } else if (type === 'content_block_start') {
      const cb = record.content_block as Record<string, unknown> | undefined;
      if (cb?.type === 'tool_use' && typeof cb.name === 'string') {
        onDelta(`\n> Using tool: ${cb.name}\n`);
      }
    } else if (type === 'result') {
      gotResult = true;
      cliSessionId = (record.session_id as string) || null;
      costUsd = typeof record.cost_usd === 'number' ? record.cost_usd : null;
      const usage = record.usage as Record<string, number> | undefined;
      inputTokens = usage?.input_tokens;
      outputTokens = usage?.output_tokens;
      durationMs = typeof record.duration_ms === 'number' ? record.duration_ms : undefined;

      if (record.is_error) {
        onError({ message: (record.result as string) || 'Unknown error', code: 'cli_error' });
        return;
      }

      // Fallback: if no content_block_delta events were received but result
      // contains text, emit the full result text at once.
      if (!gotDelta && typeof record.result === 'string' && record.result) {
        onDelta(record.result);
      }

      // Complete immediately on result event — don't wait for process exit.
      // Claude CLI with --verbose may stay alive after emitting result.
      if (!completeCalled) {
        completeCalled = true;
        onComplete({ cliSessionId, costUsd, inputTokens, outputTokens, durationMs });
      }
    }
  });

  proc.stderr?.on('data', (chunk: Buffer) => {
    stderrBuf += chunk.toString();
  });

  const promise = new Promise<void>((resolve) => {
    proc.on('close', (code) => {
      rl.close();

      if (cancelled) {
        resolve();
        return;
      }

      // Check if stream-json is unsupported
      if (code !== 0 && !gotResult && (stderrBuf.includes('unknown') || stderrBuf.includes('Invalid value'))) {
        claudeStreamJsonSupported = false;
        console.warn('[cliAdapter] stream-json not supported, falling back to json mode');
        const fallback = runClaudeJson(params);
        fallback.promise.then(resolve);
        return;
      }

      if (!gotResult && code !== 0) {
        onError({
          message: stderrBuf.trim() || `Process exited with code ${code}`,
          code: 'process_error',
        });
      }
      // onComplete already called from result event — no need to call again here

      resolve();
    });

    // Timeout
    setTimeout(() => {
      if (proc.exitCode === null && !proc.killed) {
        cancelled = true;
        cancelProcess(proc);
        onError({ message: 'Request timed out', code: 'timeout' });
        resolve();
      }
    }, MESSAGE_TIMEOUT_MS);
  });

  return {
    cancel() {
      cancelled = true;
      cancelProcess(proc);
    },
    promise,
  };
}

function runClaudeJson(params: RunParams): RunHandle {
  const { backend, cwd, onDelta, onComplete, onError } = params;
  const args = buildClaudeArgs(params, false);

  let cancelled = false;
  const proc = spawn(backend.binary, args, {
    cwd,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env },
  });

  let stdoutBuf = '';
  let stderrBuf = '';

  proc.stdout?.on('data', (chunk: Buffer) => {
    stdoutBuf += chunk.toString();
  });

  proc.stderr?.on('data', (chunk: Buffer) => {
    stderrBuf += chunk.toString();
  });

  const promise = new Promise<void>((resolve) => {
    proc.on('close', (code) => {
      if (cancelled) { resolve(); return; }

      let parsed: Record<string, unknown>;
      try {
        parsed = JSON.parse(stdoutBuf.trim());
      } catch {
        onError({
          message: stderrBuf.trim() || `Failed to parse response (exit code ${code})`,
          code: 'parse_error',
        });
        resolve();
        return;
      }

      if (parsed.is_error) {
        onError({ message: (parsed.result as string) || 'Unknown error', code: 'cli_error' });
        resolve();
        return;
      }

      const text = (parsed.result as string) || '';
      if (text) onDelta(text);

      onComplete({
        cliSessionId: (parsed.session_id as string) || null,
        costUsd: typeof parsed.cost_usd === 'number' ? parsed.cost_usd : null,
        inputTokens: (parsed.usage as Record<string, number>)?.input_tokens,
        outputTokens: (parsed.usage as Record<string, number>)?.output_tokens,
      });

      resolve();
    });

    setTimeout(() => {
      if (proc.exitCode === null && !proc.killed) {
        cancelled = true;
        cancelProcess(proc);
        onError({ message: 'Request timed out', code: 'timeout' });
        resolve();
      }
    }, MESSAGE_TIMEOUT_MS);
  });

  return {
    cancel() { cancelled = true; cancelProcess(proc); },
    promise,
  };
}

// === OpenCode ===

function runOpenCode(params: RunParams): RunHandle {
  const { backend, prompt, cwd, model, cliSessionId, onDelta, onComplete, onError } = params;

  const args = ['run', '--dir', cwd, '--format', 'json'];
  if (model) args.push('--model', model);
  if (cliSessionId) args.push('--session', cliSessionId);
  args.push(prompt);

  let cancelled = false;

  // Snapshot language-server PIDs before spawn
  const beforePids = getLanguageServerPids();

  const proc = spawn(backend.binary, args, {
    cwd,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env },
  });

  let sessionId: string | null = null;
  let errorOccurred = false;
  let stderrBuf = '';

  const rl = createInterface({ input: proc.stdout! });

  rl.on('line', (line: string) => {
    if (cancelled) return;
    const trimmed = line.trim();
    if (!trimmed) return;

    let record: Record<string, unknown>;
    try {
      record = JSON.parse(trimmed);
    } catch {
      return; // Skip malformed lines
    }

    // Extract session ID (first one wins)
    if (!sessionId) {
      const sid = record.sessionID as string | undefined;
      if (sid) sessionId = sid;
    }

    const type = record.type as string;

    if (type === 'session.create') {
      const props = record.properties as Record<string, unknown> | undefined;
      if (props?.sessionID && !sessionId) {
        sessionId = props.sessionID as string;
      }
    } else if (type === 'text') {
      const part = record.part;
      if (typeof part === 'string') {
        onDelta(part);
      } else if (part && typeof part === 'object' && 'text' in part) {
        onDelta((part as Record<string, string>).text || '');
      }
    } else if (type === 'error') {
      errorOccurred = true;
      const error = record.error as Record<string, unknown> | undefined;
      const data = error?.data as Record<string, string> | undefined;
      const msg = data?.message || error?.name as string || 'Unknown OpenCode error';
      onError({ message: msg, code: 'cli_error' });
    }
  });

  proc.stderr?.on('data', (chunk: Buffer) => {
    stderrBuf += chunk.toString();
  });

  const promise = new Promise<void>((resolve) => {
    proc.on('close', (code) => {
      rl.close();

      // Cleanup orphan language-server processes
      const afterPids = getLanguageServerPids();
      killOrphanPids(beforePids, afterPids);

      if (cancelled) { resolve(); return; }

      if (!errorOccurred && code !== 0) {
        onError({
          message: stderrBuf.trim() || `OpenCode exited with code ${code}`,
          code: 'process_error',
        });
      } else if (!errorOccurred) {
        onComplete({
          cliSessionId: sessionId,
          costUsd: null, // OpenCode doesn't track cost
        });
      }

      resolve();
    });

    setTimeout(() => {
      if (proc.exitCode === null && !proc.killed) {
        cancelled = true;
        cancelProcess(proc);
        onError({ message: 'Request timed out', code: 'timeout' });
        resolve();
      }
    }, MESSAGE_TIMEOUT_MS);
  });

  return {
    cancel() { cancelled = true; cancelProcess(proc); },
    promise,
  };
}

// === Public API ===

export function runCli(params: RunParams): RunHandle {
  if (params.backend.name === 'claude-cli') {
    if (claudeStreamJsonSupported) {
      return runClaudeStreaming(params);
    }
    return runClaudeJson(params);
  }
  return runOpenCode(params);
}
