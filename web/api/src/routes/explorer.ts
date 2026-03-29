import { Router, Request, Response } from 'express';
import { explorerService } from '../services/explorerService.js';

const router = Router();

// GET /api/explorer/roots — Get filesystem starting points
router.get('/roots', async (_req: Request, res: Response) => {
  try {
    const roots = await explorerService.getRoots();
    res.json(roots);
  } catch (error) {
    console.error('Explorer roots error:', error);
    res.status(500).json({ error: 'Failed to get filesystem roots' });
  }
});

// GET /api/explorer/list?path=/some/path — List subdirectories
router.get('/list', async (req: Request, res: Response) => {
  try {
    const dirPath = req.query.path;
    if (typeof dirPath !== 'string' || !dirPath) {
      res.status(400).json({ error: 'Missing required query parameter: path' });
      return;
    }

    const entries = await explorerService.listDirectories(dirPath);
    if (entries === null) {
      res.status(403).json({ error: 'Path is not accessible' });
      return;
    }

    res.json({ path: dirPath, entries });
  } catch (error) {
    console.error('Explorer list error:', error);
    res.status(500).json({ error: 'Failed to list directory' });
  }
});

// GET /api/explorer/validate?path=/some/path — Check if path is a valid KB root
router.get('/validate', async (req: Request, res: Response) => {
  try {
    const dirPath = req.query.path;
    if (typeof dirPath !== 'string' || !dirPath) {
      res.status(400).json({ error: 'Missing required query parameter: path' });
      return;
    }

    const validation = await explorerService.validateKbRoot(dirPath);
    res.json(validation);
  } catch (error) {
    console.error('Explorer validate error:', error);
    res.status(500).json({ error: 'Failed to validate path' });
  }
});

export default router;
