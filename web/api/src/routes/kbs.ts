import { Router, Request, Response } from 'express';
import { kbService } from '../services/kbService.js';

const router = Router();

// GET /api/kbs — List all discovered KBs
router.get('/', async (_req: Request, res: Response) => {
  try {
    const kbs = await kbService.list();
    res.json({ kbs, total: kbs.length });
  } catch (error) {
    res.status(500).json({ error: 'Failed to list knowledge bases' });
  }
});

// GET /api/kbs/:name — Get a single KB's metadata
router.get('/:name', async (req: Request, res: Response) => {
  try {
    const kb = await kbService.get(req.params.name);
    if (!kb) {
      res.status(404).json({ error: 'Knowledge base not found' });
      return;
    }
    res.json(kb);
  } catch (error) {
    res.status(500).json({ error: 'Failed to get knowledge base' });
  }
});

export default router;
