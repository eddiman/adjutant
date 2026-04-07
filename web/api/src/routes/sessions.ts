/**
 * REST routes for code session management.
 *
 * Thin REST endpoints for session listing/deletion. The actual chat flow
 * goes through the WebSocket at /ws/code-session.
 */

import { Router } from 'express';
import fs from 'fs';
import path from 'path';
import readline from 'readline';
import { sessionService } from '../services/sessionService.js';
import { backendDetector } from '../services/backendDetector.js';

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
  return dirName.replace(/^-/, '/').replace(/-/g, '/');
}

async function scanClaudeCliSessions(limit = 50): Promise<CliSessionSummary[]> {
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
    const cwd = decodeCwdFromDirName(projDir);
    const projPath = path.join(claudeDir, projDir);
    let files: string[];
    try {
      files = fs.readdirSync(projPath).filter(f => f.endsWith('.jsonl'));
    } catch { continue; }

    for (const file of files) {
      const sessionId = file.replace('.jsonl', '');
      const filePath = path.join(projPath, file);

      let stat: fs.Stats;
      try { stat = fs.statSync(filePath); } catch { continue; }

      // Read first few lines to extract metadata
      let firstUserText = '';
      let model = '';
      let timestamp = stat.mtime.toISOString();
      let msgCount = 0;

      try {
        const stream = fs.createReadStream(filePath, { encoding: 'utf-8' });
        const rl = readline.createInterface({ input: stream });
        let linesRead = 0;

        for await (const line of rl) {
          if (linesRead++ > 20) break; // only scan first 20 lines
          try {
            const record = JSON.parse(line);
            if (record.type === 'user' && !firstUserText) {
              const content = record.message?.content;
              if (Array.isArray(content)) {
                const textBlock = content.find((c: { type: string }) => c.type === 'text');
                if (textBlock) firstUserText = textBlock.text?.slice(0, 80) || '';
              }
              if (record.timestamp) timestamp = record.timestamp;
              if (record.cwd) timestamp = record.timestamp; // use first user msg timestamp
            }
            if (record.type === 'assistant' && !model) {
              model = record.message?.model || '';
            }
            if (record.type === 'user' || record.type === 'assistant') msgCount++;
          } catch { /* skip malformed */ }
        }
        rl.close();
        stream.destroy();
      } catch { continue; }

      sessions.push({
        id: sessionId,
        name: firstUserText || 'Untitled session',
        cwd,
        model,
        timestamp,
        messageCount: msgCount,
        source: 'cli',
      });
    }
  }

  // Sort by timestamp descending, limit
  sessions.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
  return sessions.slice(0, limit);
}

// GET /api/sessions — list all sessions (web + CLI)
router.get('/', async (_req, res) => {
  const webSessions = sessionService.list();
  const cliSessions = await scanClaudeCliSessions();
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
