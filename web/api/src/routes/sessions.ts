/**
 * REST routes for code session management.
 *
 * Thin REST endpoints for session listing/deletion. The actual chat flow
 * goes through the WebSocket at /ws/code-session.
 */

import { Router } from 'express';
import fs from 'fs';
import os from 'os';
import path from 'path';
import readline from 'readline';
import { execSync } from 'child_process';
import { sessionService } from '../services/sessionService.js';
import { backendDetector } from '../services/backendDetector.js';
import type { ChatMessage } from '../types/session.js';

const router = Router();

// === Claude CLI session discovery ===

interface CliSessionSummary {
  id: string;
  name: string;
  cwd: string;
  model: string;
  timestamp: string;
  messageCount: number;
  source: 'cli';
}

function decodeCwdFromDirName(dirName: string): string {
  // ~/.claude/projects/ dirs encode paths: /Users/foo → -Users-foo
  //
  // NOTE: This encoding is lossy — Claude CLI replaces BOTH `/` and `_`
  // (and keeps existing `-`) all as `-`, so paths like
  // `/Volumes/Mandalor/JottaSync/AI_knowledge_bases/munich-summer2026`
  // cannot be reliably recovered from the directory name alone. Callers
  // should prefer the real `cwd` field read out of the JSONL records;
  // this function is only the last-resort fallback.
  return dirName.replace(/^-/, '/').replace(/-/g, '/');
}

/**
 * Extract preview text from a user record's `message.content`, handling
 * both the string and array-of-content-blocks shapes. Returns an empty
 * string if no text is found.
 */
function extractUserText(content: unknown): string {
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) {
    const textBlock = content.find(
      (c: unknown): c is { type: string; text?: string } =>
        typeof c === 'object' && c !== null && (c as { type?: string }).type === 'text',
    );
    if (textBlock && typeof textBlock.text === 'string') return textBlock.text;
  }
  return '';
}

/**
 * Scan a single JSONL file and build a CliSessionSummary.
 *
 * @param filePath  Absolute path to the JSONL file.
 * @param sessionId The session id to assign (usually derived from the filename).
 * @param fallbackCwd A cwd to use if the JSONL doesn't carry one — should be
 *                    the lossy decode of the parent project dir.
 * @param overrideName Optional name to use verbatim (e.g. from a sub-agent's
 *                     meta.json). When set, we still read the file to extract
 *                     cwd/model/msgCount but keep the name as-is.
 */
async function scanSessionFile(
  filePath: string,
  sessionId: string,
  fallbackCwd: string,
  overrideName?: string,
): Promise<CliSessionSummary | null> {
  let stat: fs.Stats;
  try { stat = fs.statSync(filePath); } catch { return null; }

  let firstUserText = '';
  let sidechainUserText = '';
  let model = '';
  let timestamp = stat.mtime.toISOString();
  let msgCount = 0;
  // Prefer the `cwd` field embedded in the JSONL records — the directory
  // name is a lossy encoding that cannot be reliably recovered.
  let realCwd: string | null = null;

  try {
    const stream = fs.createReadStream(filePath, { encoding: 'utf-8' });
    const rl = readline.createInterface({ input: stream });
    let linesRead = 0;

    for await (const line of rl) {
      if (linesRead++ > 20) break; // only scan first 20 lines
      try {
        const record = JSON.parse(line);
        if (!realCwd && typeof record.cwd === 'string' && record.cwd.length > 0) {
          realCwd = record.cwd;
        }
        const isSidechain = record.isSidechain === true;
        if (record.type === 'user') {
          const text = extractUserText(record.message?.content);
          if (text) {
            const collapsed = text.replace(/\s+/g, ' ').trim().slice(0, 80);
            if (!isSidechain && !firstUserText) {
              firstUserText = collapsed;
              if (record.timestamp) timestamp = record.timestamp;
            } else if (isSidechain && !sidechainUserText) {
              // Remember sidechain text as a fallback for sub-agent-only
              // files (whose every record is a sidechain by design).
              sidechainUserText = collapsed;
              if (record.timestamp && !firstUserText) timestamp = record.timestamp;
            }
          }
        }
        if (record.type === 'assistant' && !model) {
          model = record.message?.model || '';
        }
        if (record.type === 'user' || record.type === 'assistant') msgCount++;
      } catch { /* skip malformed */ }
    }
    rl.close();
    stream.destroy();
  } catch { return null; }

  const name = overrideName || firstUserText || sidechainUserText || 'Untitled session';

  return {
    id: sessionId,
    name,
    cwd: realCwd || fallbackCwd,
    model,
    timestamp,
    messageCount: msgCount,
    source: 'cli',
  };
}

/**
 * Read an optional sub-agent meta.json sibling to get a display name.
 * Returns a string like "claude-code-guide · Remote session clearing"
 * or null if the file doesn't exist / can't be parsed.
 */
function readSubagentMeta(jsonlPath: string): string | null {
  const metaPath = jsonlPath.replace(/\.jsonl$/, '.meta.json');
  try {
    const raw = fs.readFileSync(metaPath, 'utf-8');
    const parsed = JSON.parse(raw) as { agentType?: string; description?: string };
    const bits: string[] = [];
    if (parsed.agentType) bits.push(parsed.agentType);
    if (parsed.description) bits.push(parsed.description);
    if (bits.length === 0) return null;
    return bits.join(' · ').slice(0, 80);
  } catch {
    return null;
  }
}

/**
 * Claude CLI sessions on disk live in two places:
 *
 *   1. Top-level:  `~/.claude/projects/<encoded-cwd>/<session-uuid>.jsonl`
 *                  Normal user-driven sessions.
 *
 *   2. Nested sub-agent logs:
 *      `~/.claude/projects/<encoded-cwd>/<parent-uuid>/subagents/agent-<hash>.jsonl`
 *      Spawned by the parent session via the Task tool. Every record in
 *      these files is `isSidechain: true`. A sibling
 *      `agent-<hash>.meta.json` carries the agent type and a human
 *      description we use as the preview title.
 *
 * Both shapes are scanned and merged into a single list, sorted by
 * timestamp descending. The limit is a safety cap — we don't want to
 * read the entire history if the user has thousands of files — but it
 * must be high enough to comfortably hold several months of activity.
 */
async function scanClaudeCliSessions(limit = 500): Promise<CliSessionSummary[]> {
  const claudeDir = path.join(process.env.HOME || '', '.claude', 'projects');
  let projectDirs: string[];
  try {
    projectDirs = fs.readdirSync(claudeDir).filter(d => {
      try { return fs.statSync(path.join(claudeDir, d)).isDirectory(); } catch { return false; }
    });
  } catch {
    return [];
  }

  const sessions: CliSessionSummary[] = [];

  for (const projDir of projectDirs) {
    const fallbackCwd = decodeCwdFromDirName(projDir);
    const projPath = path.join(claudeDir, projDir);

    // --- Top-level session files ---
    let topLevelFiles: string[];
    try {
      topLevelFiles = fs.readdirSync(projPath).filter(f => f.endsWith('.jsonl'));
    } catch { continue; }

    for (const file of topLevelFiles) {
      const sessionId = file.replace('.jsonl', '');
      const summary = await scanSessionFile(path.join(projPath, file), sessionId, fallbackCwd);
      if (summary) sessions.push(summary);
    }

    // --- Nested sub-agent files: <projPath>/<parent-uuid>/subagents/*.jsonl ---
    let subdirs: string[];
    try {
      subdirs = fs.readdirSync(projPath).filter(d => {
        try { return fs.statSync(path.join(projPath, d)).isDirectory(); } catch { return false; }
      });
    } catch { subdirs = []; }

    for (const subdir of subdirs) {
      const subagentsDir = path.join(projPath, subdir, 'subagents');
      let agentFiles: string[];
      try {
        agentFiles = fs.readdirSync(subagentsDir).filter(f => f.endsWith('.jsonl'));
      } catch { continue; }

      for (const file of agentFiles) {
        const agentFilePath = path.join(subagentsDir, file);
        const sessionId = file.replace('.jsonl', '');
        const metaTitle = readSubagentMeta(agentFilePath);
        const summary = await scanSessionFile(
          agentFilePath,
          sessionId,
          fallbackCwd,
          metaTitle || undefined,
        );
        if (summary) sessions.push(summary);
      }
    }
  }

  // Sort by timestamp descending, cap at `limit` as a safety valve.
  sessions.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
  return sessions.slice(0, limit);
}

/**
 * Read full message history from a Claude CLI session JSONL file.
 * Returns ChatMessage[] suitable for pre-populating a web session.
 */
export async function readCliSessionMessages(sessionId: string): Promise<ChatMessage[]> {
  const claudeDir = path.join(process.env.HOME || '', '.claude', 'projects');
  let projectDirs: string[];
  try {
    projectDirs = fs.readdirSync(claudeDir).filter(d => {
      try { return fs.statSync(path.join(claudeDir, d)).isDirectory(); } catch { return false; }
    });
  } catch { return []; }

  // Find the JSONL file across all project dirs
  let filePath: string | null = null;
  for (const projDir of projectDirs) {
    const candidate = path.join(claudeDir, projDir, `${sessionId}.jsonl`);
    if (fs.existsSync(candidate)) { filePath = candidate; break; }
  }
  if (!filePath) return [];

  const messages: ChatMessage[] = [];
  const seenUuids = new Set<string>();

  try {
    const stream = fs.createReadStream(filePath, { encoding: 'utf-8' });
    const rl = readline.createInterface({ input: stream });

    for await (const line of rl) {
      try {
        const record = JSON.parse(line);
        const uuid = record.uuid as string | undefined;

        if (record.type === 'user' && uuid && !seenUuids.has(uuid)) {
          seenUuids.add(uuid);
          const content = record.message?.content;
          let text = '';
          if (Array.isArray(content)) {
            text = content
              .filter((c: { type: string }) => c.type === 'text')
              .map((c: { text: string }) => c.text)
              .join('\n');
          } else if (typeof content === 'string') {
            text = content;
          }
          if (text) {
            messages.push({
              id: uuid,
              role: 'user',
              content: text,
              timestamp: record.timestamp || new Date().toISOString(),
            });
          }
        } else if (record.type === 'assistant' && uuid && !seenUuids.has(uuid)) {
          seenUuids.add(uuid);
          const content = record.message?.content;
          let text = '';
          if (Array.isArray(content)) {
            text = content
              .filter((c: { type: string }) => c.type === 'text')
              .map((c: { text: string }) => c.text)
              .join('\n');
          }
          if (text) {
            messages.push({
              id: uuid,
              role: 'assistant',
              content: text,
              timestamp: record.timestamp || new Date().toISOString(),
              model: record.message?.model,
            });
          }
        }
      } catch { /* skip malformed lines */ }
    }

    rl.close();
    stream.destroy();
  } catch { /* file read error */ }

  return messages;
}

// === OpenCode session discovery ===

/**
 * Scan OpenCode sessions via `opencode session list --format json`.
 *
 * OpenCode stores sessions in a SQLite database (~/.local/share/opencode/).
 * Rather than adding a SQLite driver dependency, we shell out to the CLI
 * which returns structured JSON.
 */
async function scanOpenCodeSessions(binary: string, limit = 500): Promise<CliSessionSummary[]> {
  // OpenCode truncates stdout at 8 KB when writing to a pipe (unflushed Go
  // writer).  Work around this by redirecting output through a temp file.
  const tmp = path.join(os.tmpdir(), `adjutant-oc-sessions-${Date.now()}.json`);
  let raw: string;
  try {
    execSync(`${binary} session list --format json -n ${limit} > ${tmp}`, {
      timeout: 10000,
      maxBuffer: 10 * 1024 * 1024,
      shell: true,
    });
    raw = fs.readFileSync(tmp, 'utf-8');
  } catch {
    return [];
  } finally {
    try { fs.unlinkSync(tmp); } catch { /* ignore */ }
  }

  let records: Array<{
    id?: string;
    title?: string;
    directory?: string;
    updated?: number;
    created?: number;
  }>;
  try {
    records = JSON.parse(raw);
    if (!Array.isArray(records)) return [];
  } catch {
    return [];
  }

  return records
    .filter(r => r.id && typeof r.id === 'string')
    .map(r => ({
      id: r.id!,
      name: r.title || 'Untitled session',
      cwd: r.directory || '',
      model: '',
      // OpenCode timestamps are epoch milliseconds
      timestamp: r.updated ? new Date(r.updated).toISOString() : new Date().toISOString(),
      messageCount: 0,
      source: 'cli' as const,
    }));
}

/**
 * Read full message history from an OpenCode session via `opencode export <id>`.
 *
 * The export JSON contains `messages[]` with `info.role`, `parts[]` with
 * `type: "text"` entries. We extract user and assistant text messages.
 */
export async function readOpenCodeSessionMessages(binary: string, sessionId: string): Promise<ChatMessage[]> {
  // Same pipe-truncation workaround as scanOpenCodeSessions.
  const tmp = path.join(os.tmpdir(), `adjutant-oc-export-${Date.now()}.json`);
  let raw: string;
  try {
    execSync(`${binary} export ${sessionId} > ${tmp}`, {
      timeout: 30000,
      maxBuffer: 10 * 1024 * 1024,
      shell: true,
    });
    raw = fs.readFileSync(tmp, 'utf-8');
  } catch {
    return [];
  } finally {
    try { fs.unlinkSync(tmp); } catch { /* ignore */ }
  }

  let exported: {
    messages?: Array<{
      info?: {
        id?: string;
        role?: string;
        modelID?: string;
        time?: { created?: number; completed?: number };
      };
      parts?: Array<{
        type?: string;
        text?: string;
      }>;
    }>;
  };
  try {
    exported = JSON.parse(raw);
  } catch {
    return [];
  }

  if (!exported.messages || !Array.isArray(exported.messages)) return [];

  const messages: ChatMessage[] = [];
  for (const msg of exported.messages) {
    const role = msg.info?.role;
    if (role !== 'user' && role !== 'assistant') continue;

    // Extract text from parts
    const textParts = (msg.parts || [])
      .filter(p => p.type === 'text' && typeof p.text === 'string')
      .map(p => p.text!);

    const text = textParts.join('\n');
    if (!text) continue;

    const timeMs = msg.info?.time?.created;

    messages.push({
      id: msg.info?.id || `oc-${messages.length}`,
      role: role as 'user' | 'assistant',
      content: text,
      timestamp: timeMs ? new Date(timeMs).toISOString() : new Date().toISOString(),
      model: role === 'assistant' ? msg.info?.modelID : undefined,
    });
  }

  return messages;
}

// GET /api/sessions — list all sessions (web + CLI)
router.get('/', async (_req, res) => {
  const webSessions = sessionService.list();
  const backend = await backendDetector.detect();

  let cliSessions: CliSessionSummary[];
  if (backend?.name === 'opencode') {
    cliSessions = await scanOpenCodeSessions(backend.binary);
  } else {
    cliSessions = await scanClaudeCliSessions();
  }

  res.json({ sessions: webSessions, cliSessions });
});

// GET /api/sessions/backend-info — get detected backend info
router.get('/backend-info', async (_req, res) => {
  const backend = await backendDetector.detect();
  if (!backend) {
    res.json({ available: false, error: 'No CLI backend configured or binary not found' });
    return;
  }
  res.json({ available: true, backend });
});

// GET /api/sessions/:id — get a specific session
router.get('/:id', (req, res) => {
  const session = sessionService.get(req.params.id);
  if (!session) {
    res.status(404).json({ error: 'Session not found' });
    return;
  }
  res.json({ session });
});

// DELETE /api/sessions/:id — delete a session
router.delete('/:id', (req, res) => {
  const deleted = sessionService.delete(req.params.id);
  if (!deleted) {
    res.status(404).json({ error: 'Session not found' });
    return;
  }
  res.json({ deleted: true });
});

export default router;
