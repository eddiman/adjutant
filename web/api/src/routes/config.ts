import { Router, Request, Response } from 'express';
import { exec, spawn } from 'child_process';
import { configService } from '../services/configService.js';

const router = Router();

// GET /api/config — Get current app config
router.get('/', async (_req: Request, res: Response) => {
  try {
    const appConfig = await configService.get();
    res.json(appConfig);
  } catch (error) {
    res.status(500).json({ error: 'Failed to read config' });
  }
});

// PUT /api/config — Update app config
router.put('/', async (req: Request, res: Response) => {
  try {
    const updated = await configService.update(req.body);
    res.json(updated);
  } catch (error) {
    if (error instanceof Error) {
      res.status(400).json({ error: error.message });
    } else {
      res.status(500).json({ error: 'Failed to update config' });
    }
  }
});

// POST /api/config/browse — Open native directory picker (macOS Finder)
router.post('/browse', async (_req: Request, res: Response) => {
  try {
    const platform = process.platform;

    if (platform === 'darwin') {
      // macOS: use AppleScript to open Finder folder picker
      const script = `osascript -e 'try' -e 'set chosenFolder to POSIX path of (choose folder with prompt "Select KB root directory")' -e 'return chosenFolder' -e 'on error' -e 'return ""' -e 'end try'`;

      exec(script, { timeout: 0 }, (error, stdout, stderr) => {
        if (stderr) console.error('osascript stderr:', stderr);
        if (error) {
          console.error('osascript error:', error.message);
          res.json({ path: null, cancelled: true });
          return;
        }
        const selected = stdout.trim();
        if (!selected) {
          res.json({ path: null, cancelled: true });
          return;
        }
        // Remove trailing slash if present
        const cleanPath = selected.endsWith('/') ? selected.slice(0, -1) : selected;
        res.json({ path: cleanPath, cancelled: false });
      });
    } else if (platform === 'linux') {
      // Linux: try zenity
      exec('zenity --file-selection --directory --title="Select KB root directory"', { timeout: 0 }, (error, stdout) => {
        if (error) {
          res.json({ path: null, cancelled: true });
          return;
        }
        const selected = stdout.trim();
        if (!selected) {
          res.json({ path: null, cancelled: true });
          return;
        }
        res.json({ path: selected, cancelled: false });
      });
    } else {
      res.status(501).json({ error: 'Native directory picker not supported on this platform' });
    }
  } catch (error) {
    res.status(500).json({ error: 'Failed to open directory picker' });
  }
});

// POST /api/config/reveal — Open a path in native file manager
router.post('/reveal', async (req: Request, res: Response) => {
  try {
    const { path: targetPath } = req.body;
    if (!targetPath || typeof targetPath !== 'string') {
      res.status(400).json({ error: 'Missing required field: path' });
      return;
    }

    const platform = process.platform;
    let command: string;
    let args: string[];

    if (platform === 'darwin') {
      command = 'open';
      args = [targetPath];
    } else if (platform === 'linux') {
      command = 'xdg-open';
      args = [targetPath];
    } else if (platform === 'win32') {
      command = 'explorer';
      args = [targetPath];
    } else {
      res.status(501).json({ error: 'Not supported on this platform' });
      return;
    }

    let responded = false;
    const proc = spawn(command, args);

    // Kill the process after 5 seconds if it hasn't exited
    const killTimer = setTimeout(() => {
      proc.kill();
    }, 5000);

    proc.on('error', (error) => {
      clearTimeout(killTimer);
      if (responded) return;
      responded = true;
      console.error('Failed to open in file manager:', error);
      res.status(500).json({ error: 'Failed to open in file manager' });
    });

    proc.on('exit', (code) => {
      clearTimeout(killTimer);
      if (responded) return;
      responded = true;
      if (code === 0 || code === null) {
        res.json({ success: true });
      } else {
        res.status(500).json({ error: 'Failed to open in file manager' });
      }
    });
  } catch (error) {
    res.status(500).json({ error: 'Failed to reveal path' });
  }
});

export default router;
