/**
 * REST routes for code session management.
 *
 * Thin REST endpoints for session listing/deletion. The actual chat flow
 * goes through the WebSocket at /ws/code-session.
 */

import { Router } from 'express';
import { sessionService } from '../services/sessionService.js';
import { backendDetector } from '../services/backendDetector.js';

const router = Router();

// GET /api/sessions — list all sessions
router.get('/', (_req, res) => {
  res.json({ sessions: sessionService.list() });
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
