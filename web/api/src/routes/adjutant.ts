/**
 * Adjutant integration routes.
 *
 * Exposes Adjutant lifecycle state and mode information to the web UI.
 * These endpoints only return data when Adjutant integration is available.
 */

import { Router, Request, Response } from 'express';
import fs from 'fs/promises';
import path from 'path';
import { spawn } from 'child_process';
import { registryService } from '../services/registryService.js';
import { kbService } from '../services/kbService.js';
import { backendDetector } from '../services/backendDetector.js';

const router = Router();

// === Process Detection Helpers ===

/**
 * Check if a PID is alive (equivalent to `kill -0` / Adjutant's pid_is_alive).
 *
 * Returns true if the process exists. EPERM means it exists but we can't
 * signal it — still alive.
 */
function pidIsAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch (err: unknown) {
    if (err instanceof Error && 'code' in err && (err as NodeJS.ErrnoException).code === 'EPERM') {
      return true; // Process exists, we just can't signal it
    }
    return false; // ESRCH = no such process
  }
}

/**
 * Read a PID file and return the PID if the process is alive.
 * Returns null if the file doesn't exist, is unreadable, or the PID is dead.
 */
async function readAlivePid(filePath: string): Promise<number | null> {
  try {
    const content = await fs.readFile(filePath, 'utf-8');
    const pid = parseInt(content.trim(), 10);
    if (isNaN(pid)) return null;
    return pidIsAlive(pid) ? pid : null;
  } catch {
    return null;
  }
}

/**
 * Find the running Adjutant listener PID using the same priority as
 * Adjutant's own service.py:_find_listener_pid:
 *
 *   1. state/listener.lock/pid — written by the listener itself
 *   2. state/telegram.pid — written by the launcher
 *
 * (Skips psutil/process-scan — not available in Node; PID files are sufficient.)
 */
async function findListenerPid(adjDir: string): Promise<number | null> {
  // Priority 1: listener.lock/pid (authoritative — written by the listener)
  const lockPid = await readAlivePid(path.join(adjDir, 'state', 'listener.lock', 'pid'));
  if (lockPid !== null) return lockPid;

  // Priority 2: telegram.pid (written by the launcher)
  const telegramPid = await readAlivePid(path.join(adjDir, 'state', 'telegram.pid'));
  if (telegramPid !== null) return telegramPid;

  return null;
}

/**
 * GET /api/adjutant/status — Adjutant integration status.
 *
 * Returns:
 * - mode: 'adjutant' | 'standalone'
 * - available: whether Adjutant directory was found
 * - adjutantDir: path to Adjutant directory (if available)
 * - lifecycleState: OPERATIONAL | PAUSED | KILLED | STOPPED (read from state files + process check)
 * - processRunning: whether the listener process is alive
 * - listenerPid: PID of the running listener (if alive)
 */
router.get('/status', async (_req: Request, res: Response) => {
  try {
    const mode = await kbService.getMode();
    const adjDir = await registryService.resolveAdjutantDir();

    const result: Record<string, unknown> = {
      mode,
      available: adjDir !== null,
    };

    // Include configured backend name so the frontend doesn't have to guess.
    const backendInfo = await backendDetector.detect();
    if (backendInfo) {
      result.backendName = backendInfo.name;
    }

    if (adjDir) {
      result.adjutantDir = adjDir;

      // Read lifecycle state from filesystem markers + process check
      const listenerPid = await findListenerPid(adjDir);
      result.processRunning = listenerPid !== null;
      if (listenerPid !== null) {
        result.listenerPid = listenerPid;
      }

      try {
        await fs.access(path.join(adjDir, 'KILLED'));
        result.lifecycleState = 'KILLED';
      } catch {
        try {
          await fs.access(path.join(adjDir, 'PAUSED'));
          result.lifecycleState = 'PAUSED';
        } catch {
          result.lifecycleState = listenerPid !== null ? 'OPERATIONAL' : 'STOPPED';
        }
      }

      // Active operation (running pulse/review)
      try {
        const opFile = path.join(adjDir, 'state', 'active_operation.json');
        const opRaw = await fs.readFile(opFile, 'utf-8');
        const opData = JSON.parse(opRaw);

        // Staleness check: >30 min and PID is dead
        const startedAt = new Date(opData.started_at);
        const ageMs = Date.now() - startedAt.getTime();
        if (ageMs > 30 * 60 * 1000) {
          let pidAlive = false;
          try {
            process.kill(opData.pid, 0);
            pidAlive = true;
          } catch {
            // PID is dead
          }
          if (!pidAlive) {
            // Stale marker — clean up and ignore
            await fs.unlink(opFile).catch(() => {});
          } else {
            result.activeOperation = opData;
          }
        } else {
          result.activeOperation = opData;
        }
      } catch {
        // No active operation file — normal state
      }

      // Last heartbeat
      try {
        const hbFile = path.join(adjDir, 'state', 'last_heartbeat.json');
        const hbRaw = await fs.readFile(hbFile, 'utf-8');
        result.lastHeartbeat = JSON.parse(hbRaw);
      } catch {
        // No heartbeat data yet
      }
    }

    res.json(result);
  } catch (error) {
    res.status(500).json({ error: 'Failed to get Adjutant status' });
  }
});

/**
 * POST /api/adjutant/kb/query — Query a KB via Adjutant's sub-agent.
 *
 * This is a pass-through to `adjutant kb query <name> "<question>"`.
 * Only available when Adjutant integration is active and the adjutant
 * CLI is on PATH.
 *
 * Body: { kb: string, question: string }
 * Returns: { answer: string, source: string }
 */
router.post('/kb/query', async (req: Request, res: Response) => {
  try {
    const { kb: kbName, question } = req.body;

    if (!kbName || !question) {
      res.status(400).json({ error: 'Missing required fields: kb, question' });
      return;
    }

    const adjDir = await registryService.resolveAdjutantDir();
    if (!adjDir) {
      res.status(503).json({ error: 'Adjutant integration not available' });
      return;
    }

    // Verify the KB exists
    const kb = await kbService.get(kbName);
    if (!kb) {
      res.status(404).json({ error: `Knowledge base "${kbName}" not found` });
      return;
    }

    // Shell out to adjutant CLI
    const { spawn } = await import('child_process');
    const adjutantBin = path.join(adjDir, 'adjutant');

    // Check if the adjutant CLI exists
    try {
      await fs.access(adjutantBin);
    } catch {
      res.status(503).json({ error: 'Adjutant CLI not found. Is Adjutant installed?' });
      return;
    }

    const proc = spawn(adjutantBin, ['kb', 'query', kbName, question], {
      cwd: adjDir,
      env: { ...process.env, ADJ_DIR: adjDir },
    });

    let stdout = '';
    let stderr = '';
    let responded = false;

    // 60-second timeout (spawn doesn't support timeout option)
    const killTimer = setTimeout(() => {
      proc.kill();
    }, 60_000);

    proc.stdout.on('data', (data: Buffer) => { stdout += data.toString(); });
    proc.stderr.on('data', (data: Buffer) => { stderr += data.toString(); });

    proc.on('error', (error) => {
      clearTimeout(killTimer);
      if (responded) return;
      responded = true;
      console.error('KB query process error:', error);
      res.status(500).json({ error: 'Failed to execute KB query' });
    });

    proc.on('exit', (code) => {
      clearTimeout(killTimer);
      if (responded) return;
      responded = true;
      if (code === 0 || code === null) {
        res.json({
          answer: stdout.trim(),
          kb: kbName,
          question,
        });
      } else {
        console.error('KB query failed:', stderr);
        res.status(500).json({
          error: 'KB query failed',
          details: stderr.trim() || `Process exited with code ${code}`,
        });
      }
    });
  } catch (error) {
    console.error('KB query error:', error);
    res.status(500).json({ error: 'Failed to query knowledge base' });
  }
});

/**
 * GET /api/adjutant/schedules — List scheduled jobs from adjutant.yaml.
 *
 * Returns an array of schedule entries with name, description, schedule (cron),
 * enabled status, and last run info if available.
 */
router.get('/schedules', async (_req: Request, res: Response) => {
  try {
    const adjDir = await registryService.resolveAdjutantDir();
    if (!adjDir) {
      res.status(503).json({ error: 'Adjutant integration not available' });
      return;
    }

    const configPath = path.join(adjDir, 'adjutant.yaml');
    const yamlContent = await fs.readFile(configPath, 'utf-8');
    
    // Parse YAML manually to extract schedules block
    const schedulesMatch = yamlContent.match(/schedules:\s*([\s\S]*?)(?=\n\w|$)/);
    if (!schedulesMatch) {
      res.json({ schedules: [] });
      return;
    }

    // Simple YAML parsing for schedule entries
    const scheduleBlocks = schedulesMatch[1].split(/\n\s*-\s+name:/);
    const schedules = scheduleBlocks
      .slice(1) // Skip empty first element
      .map(block => {
        const lines = block.split('\n');
        const entry: Record<string, string | boolean> = {};
        
        lines.forEach(line => {
          const match = line.match(/^\s*(\w+):\s*["']?([^"'\n]+)["']?/);
          if (match) {
            const [, key, value] = match;
            entry[key] = value === 'true' || value === 'false' ? value === 'true' : value.trim();
          }
        });

        // Extract name from the first line
        const nameMatch = lines[0].match(/^\s*["']?([^"'\n]+)["']?/);
        if (nameMatch) {
          entry.name = nameMatch[1].trim();
        }

        return entry;
      })
      .filter(entry => entry.name);

    res.json({ schedules });
  } catch (error) {
    console.error('Failed to list schedules:', error);
    res.status(500).json({ error: 'Failed to list schedules' });
  }
});

/**
 * POST /api/adjutant/schedules/toggle — Enable or disable a schedule.
 *
 * Body: { name: string, enabled: boolean }
 */
router.post('/schedules/toggle', async (req: Request, res: Response) => {
  try {
    const { name, enabled } = req.body;

    if (!name || typeof enabled !== 'boolean') {
      res.status(400).json({ error: 'Missing required fields: name, enabled' });
      return;
    }

    const adjDir = await registryService.resolveAdjutantDir();
    if (!adjDir) {
      res.status(503).json({ error: 'Adjutant integration not available' });
      return;
    }

    const adjutantBin = path.join(adjDir, 'adjutant');
    const command = enabled ? 'enable' : 'disable';
    
    const proc = spawn(adjutantBin, ['schedule', command, name], {
      cwd: adjDir,
      env: { ...process.env, ADJ_DIR: adjDir },
    });

    let stderr = '';
    proc.stderr.on('data', (data: Buffer) => { stderr += data.toString(); });

    proc.on('exit', (code) => {
      if (code === 0 || code === null) {
        res.json({ success: true, name, enabled });
      } else {
        console.error('Schedule toggle failed:', stderr);
        res.status(500).json({
          error: 'Failed to toggle schedule',
          details: stderr.trim(),
        });
      }
    });
  } catch (error) {
    console.error('Schedule toggle error:', error);
    res.status(500).json({ error: 'Failed to toggle schedule' });
  }
});

/**
 * POST /api/adjutant/schedules/run — Manually trigger a schedule.
 *
 * Body: { name: string }
 */
router.post('/schedules/run', async (req: Request, res: Response) => {
  try {
    const { name } = req.body;

    if (!name) {
      res.status(400).json({ error: 'Missing required field: name' });
      return;
    }

    const adjDir = await registryService.resolveAdjutantDir();
    if (!adjDir) {
      res.status(503).json({ error: 'Adjutant integration not available' });
      return;
    }

    const adjutantBin = path.join(adjDir, 'adjutant');
    
    const proc = spawn(adjutantBin, ['schedule', 'run', name], {
      cwd: adjDir,
      env: { ...process.env, ADJ_DIR: adjDir },
      detached: true, // Run in background
      stdio: 'ignore',
    });

    proc.unref(); // Allow parent to exit while job runs

    res.json({ success: true, message: `Schedule "${name}" triggered` });
  } catch (error) {
    console.error('Schedule run error:', error);
    res.status(500).json({ error: 'Failed to run schedule' });
  }
});

/**
 * GET /api/adjutant/identity — Get excerpts from soul, heart, and registry.
 *
 * Returns the first 500 characters from each identity file.
 */
router.get('/identity', async (_req: Request, res: Response) => {
  try {
    const adjDir = await registryService.resolveAdjutantDir();
    if (!adjDir) {
      res.status(503).json({ error: 'Adjutant integration not available' });
      return;
    }

    const identity = {
      soul: '',
      heart: '',
      registry: '',
    };

    try {
      const soulPath = path.join(adjDir, 'identity', 'soul.md');
      const soulContent = await fs.readFile(soulPath, 'utf-8');
      identity.soul = soulContent.substring(0, 1000);
    } catch {
      // File might not exist yet
    }

    try {
      const heartPath = path.join(adjDir, 'identity', 'heart.md');
      const heartContent = await fs.readFile(heartPath, 'utf-8');
      identity.heart = heartContent.substring(0, 1000);
    } catch {
      // File might not exist yet
    }

    try {
      const registryPath = path.join(adjDir, 'identity', 'registry.md');
      const registryContent = await fs.readFile(registryPath, 'utf-8');
      identity.registry = registryContent.substring(0, 1000);
    } catch {
      // File might not exist yet
    }

    res.json(identity);
  } catch (error) {
    console.error('Failed to read identity:', error);
    res.status(500).json({ error: 'Failed to read identity files' });
  }
});

/**
 * GET /api/adjutant/insights — List escalation/insight files.
 *
 * Returns entries from both `insights/pending/` (awaiting user) and
 * `insights/sent/` (already notified), newest first.  Each entry has
 * a generated id (status-relative filename), status, title (extracted
 * from the first `#` heading or filename), and an ISO timestamp parsed
 * from the filename pattern `YYYY-MM-DD-HHMM(-slug).md`.
 */
router.get('/insights', async (_req: Request, res: Response) => {
  try {
    const adjDir = await registryService.resolveAdjutantDir();
    if (!adjDir) {
      res.status(503).json({ error: 'Adjutant integration not available' });
      return;
    }

    type InsightSummary = {
      id: string;
      status: 'pending' | 'sent';
      title: string;
      filename: string;
      timestamp: string | null;
    };

    const readDir = async (status: 'pending' | 'sent'): Promise<InsightSummary[]> => {
      const dirPath = path.join(adjDir, 'insights', status);
      let files: string[];
      try {
        files = await fs.readdir(dirPath);
      } catch {
        return [];
      }

      const mdFiles = files.filter(f => f.endsWith('.md'));
      const entries = await Promise.all(mdFiles.map(async (filename): Promise<InsightSummary> => {
        let title = filename.replace(/\.md$/, '');
        try {
          const content = await fs.readFile(path.join(dirPath, filename), 'utf-8');
          const headingMatch = content.match(/^#\s+(.+?)$/m);
          if (headingMatch) {
            title = headingMatch[1].trim();
          }
        } catch {
          // Fallback to filename as title
        }

        // Parse `YYYY-MM-DD-HHMM(-slug).md` → ISO timestamp
        const tsMatch = filename.match(/^(\d{4})-(\d{2})-(\d{2})-(\d{2})(\d{2})/);
        let timestamp: string | null = null;
        if (tsMatch) {
          const [, y, mo, d, h, mi] = tsMatch;
          timestamp = `${y}-${mo}-${d}T${h}:${mi}:00`;
        }

        return {
          id: `${status}/${filename}`,
          status,
          title,
          filename,
          timestamp,
        };
      }));

      return entries;
    };

    const [pending, sent] = await Promise.all([readDir('pending'), readDir('sent')]);
    const all = [...pending, ...sent].sort((a, b) => {
      if (a.timestamp && b.timestamp) return b.timestamp.localeCompare(a.timestamp);
      if (a.timestamp) return -1;
      if (b.timestamp) return 1;
      return b.filename.localeCompare(a.filename);
    });

    res.json({ insights: all });
  } catch (error) {
    console.error('Failed to list insights:', error);
    res.status(500).json({ error: 'Failed to list insights' });
  }
});

/**
 * GET /api/adjutant/insights/:status/:filename — Read one insight file.
 *
 * `status` must be "pending" or "sent".  `filename` must match the
 * YYYY-MM-DD-HHMM(-slug).md pattern — anything else is rejected to
 * prevent path traversal.  Returns the raw markdown content.
 */
router.get('/insights/:status/:filename', async (req: Request, res: Response) => {
  try {
    const { status, filename } = req.params;
    if (status !== 'pending' && status !== 'sent') {
      res.status(400).json({ error: 'Invalid status. Must be "pending" or "sent".' });
      return;
    }
    if (!/^[\w.-]+\.md$/.test(filename)) {
      res.status(400).json({ error: 'Invalid filename.' });
      return;
    }

    const adjDir = await registryService.resolveAdjutantDir();
    if (!adjDir) {
      res.status(503).json({ error: 'Adjutant integration not available' });
      return;
    }

    const filePath = path.join(adjDir, 'insights', status, filename);
    // Resolve and verify the path stays within insights/<status>/
    const base = path.resolve(path.join(adjDir, 'insights', status));
    const resolved = path.resolve(filePath);
    if (!resolved.startsWith(base + path.sep)) {
      res.status(400).json({ error: 'Invalid path.' });
      return;
    }

    try {
      const content = await fs.readFile(resolved, 'utf-8');
      res.json({ id: `${status}/${filename}`, status, filename, content });
    } catch {
      res.status(404).json({ error: 'Insight not found' });
    }
  } catch (error) {
    console.error('Failed to read insight:', error);
    res.status(500).json({ error: 'Failed to read insight' });
  }
});

/**
 * GET /api/adjutant/journal/days — List available daily journal entries.
 *
 * Reads `journal/YYYY-MM-DD.md` files and returns a summary per day
 * (date, filename, short preview, count of `## HH:MM — ...` sections),
 * newest first.
 */
router.get('/journal/days', async (_req: Request, res: Response) => {
  try {
    const adjDir = await registryService.resolveAdjutantDir();
    if (!adjDir) {
      res.status(503).json({ error: 'Adjutant integration not available' });
      return;
    }

    const journalDir = path.join(adjDir, 'journal');
    let files: string[];
    try {
      files = await fs.readdir(journalDir);
    } catch {
      res.json({ days: [] });
      return;
    }

    const dayFiles = files.filter(f => /^\d{4}-\d{2}-\d{2}\.md$/.test(f));

    const days = await Promise.all(dayFiles.map(async filename => {
      const date = filename.replace(/\.md$/, '');
      let preview = '';
      let entryCount = 0;
      try {
        const content = await fs.readFile(path.join(journalDir, filename), 'utf-8');
        const lines = content.split('\n');
        // Count `## HH:MM — ...` section headers
        entryCount = lines.filter(l => /^##\s+\d{2}:\d{2}\s*[—–-]/.test(l)).length;
        // Preview = first non-empty, non-heading, non-bullet line (or first bullet, trimmed)
        const firstContent = lines.find(l => {
          const t = l.trim();
          return t && !t.startsWith('#');
        });
        if (firstContent) {
          preview = firstContent.trim().replace(/^[-*]\s+/, '').slice(0, 140);
        }
      } catch {
        // Unreadable — leave defaults
      }
      return { date, filename, preview, entryCount };
    }));

    days.sort((a, b) => b.date.localeCompare(a.date));
    res.json({ days });
  } catch (error) {
    console.error('Failed to list journal days:', error);
    res.status(500).json({ error: 'Failed to list journal days' });
  }
});

/**
 * GET /api/adjutant/journal/day/:date — Read one day's journal markdown.
 *
 * `date` must match YYYY-MM-DD to prevent path traversal.
 */
router.get('/journal/day/:date', async (req: Request, res: Response) => {
  try {
    const { date } = req.params;
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
      res.status(400).json({ error: 'Invalid date. Expected YYYY-MM-DD.' });
      return;
    }

    const adjDir = await registryService.resolveAdjutantDir();
    if (!adjDir) {
      res.status(503).json({ error: 'Adjutant integration not available' });
      return;
    }

    const filePath = path.join(adjDir, 'journal', `${date}.md`);
    try {
      const content = await fs.readFile(filePath, 'utf-8');
      res.json({ date, content });
    } catch {
      res.status(404).json({ error: 'Journal entry not found' });
    }
  } catch (error) {
    console.error('Failed to read journal day:', error);
    res.status(500).json({ error: 'Failed to read journal day' });
  }
});

/**
 * GET /api/adjutant/log/recent — Tail of the operational log.
 *
 * Returns the last 20 lines from `state/adjutant.log` (written by
 * Adjutant's `adj_log()` helper — not to be confused with the human-
 * readable daily journal markdown under `journal/YYYY-MM-DD.md`).
 */
router.get('/log/recent', async (_req: Request, res: Response) => {
  try {
    const adjDir = await registryService.resolveAdjutantDir();
    if (!adjDir) {
      res.status(503).json({ error: 'Adjutant integration not available' });
      return;
    }

    const logPath = path.join(adjDir, 'state', 'adjutant.log');

    try {
      const content = await fs.readFile(logPath, 'utf-8');
      const lines = content.split('\n').filter(line => line.trim());
      const recent = lines.slice(-20).reverse(); // Last 20, newest first

      res.json({ entries: recent });
    } catch {
      res.json({ entries: [] });
    }
  } catch (error) {
    console.error('Failed to read log:', error);
    res.status(500).json({ error: 'Failed to read log' });
  }
});

/**
 * GET /api/adjutant/health — Run health checks.
 *
 * Checks:
 * - Adjutant directory exists
 * - Config file exists
 * - CLI is executable
 * - Listener process is running (PID alive)
 */
router.get('/health', async (_req: Request, res: Response) => {
  try {
    const adjDir = await registryService.resolveAdjutantDir();
    
    const checks = {
      adjutantDirExists: adjDir !== null,
      configExists: false,
      cliExecutable: false,
      processRunning: false,
    };

    if (adjDir) {
      try {
        await fs.access(path.join(adjDir, 'adjutant.yaml'));
        checks.configExists = true;
      } catch {
        // Config doesn't exist
      }

      try {
        await fs.access(path.join(adjDir, 'adjutant'), fs.constants.X_OK);
        checks.cliExecutable = true;
      } catch {
        // CLI not executable
      }

      const listenerPid = await findListenerPid(adjDir);
      checks.processRunning = listenerPid !== null;
    }

    const healthy = checks.adjutantDirExists && checks.configExists
      && checks.cliExecutable && checks.processRunning;

    res.json({
      healthy,
      checks,
    });
  } catch (error) {
    console.error('Health check error:', error);
    res.status(500).json({ error: 'Health check failed' });
  }
});

/**
 * POST /api/adjutant/lifecycle — Control Adjutant lifecycle.
 *
 * Body: { action: 'pause' | 'resume' | 'pulse' | 'review' }
 *
 * pause/resume are instant — waits for completion.
 * pulse/review are long-running — fires detached and returns immediately.
 * Adjutant writes state/active_operation.json so clients can poll status.
 */
router.post('/lifecycle', async (req: Request, res: Response) => {
  try {
    const { action } = req.body;

    if (!['pause', 'resume', 'pulse', 'review'].includes(action)) {
      res.status(400).json({ error: 'Invalid action. Must be: pause, resume, pulse, or review' });
      return;
    }

    const adjDir = await registryService.resolveAdjutantDir();
    if (!adjDir) {
      res.status(503).json({ error: 'Adjutant integration not available' });
      return;
    }

    const adjutantBin = path.join(adjDir, 'adjutant');

    if (action === 'pulse' || action === 'review') {
      // Fire-and-forget — Adjutant tracks its own running state via
      // state/active_operation.json.  The client polls GET /status.
      const proc = spawn(adjutantBin, [action], {
        cwd: adjDir,
        env: { ...process.env, ADJ_DIR: adjDir },
        detached: true,
        stdio: 'ignore',
      });
      proc.unref();
      res.json({ success: true, action, message: `${action} triggered` });
    } else {
      // pause/resume are instant — wait for result
      const proc = spawn(adjutantBin, [action], {
        cwd: adjDir,
        env: { ...process.env, ADJ_DIR: adjDir },
      });

      let stdout = '';
      let stderr = '';

      proc.stdout.on('data', (data: Buffer) => { stdout += data.toString(); });
      proc.stderr.on('data', (data: Buffer) => { stderr += data.toString(); });

      proc.on('exit', (code) => {
        if (code === 0 || code === null) {
          res.json({
            success: true,
            action,
            output: stdout.trim(),
          });
        } else {
          console.error('Lifecycle action failed:', stderr);
          res.status(500).json({
            error: `Failed to ${action}`,
            details: stderr.trim(),
          });
        }
      });
    }
  } catch (error) {
    console.error('Lifecycle action error:', error);
    res.status(500).json({ error: 'Failed to execute lifecycle action' });
  }
});

export default router;
