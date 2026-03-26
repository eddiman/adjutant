/**
 * Access control middleware.
 *
 * Blocks write operations (POST, PUT, DELETE) to read-only KBs.
 * The access level comes from Adjutant's registry or the kb.yaml file.
 */

import type { Request, Response, NextFunction } from 'express';
import { kbService } from '../services/kbService.js';

/**
 * Extract the KB name from the request (query param or body).
 */
function extractKb(req: Request): string | null {
  return (req.query.kb as string) || req.body?.kb || null;
}

/**
 * Middleware that rejects write operations on read-only KBs.
 * Applies to POST, PUT, DELETE requests that target a specific KB.
 * GET requests pass through unconditionally.
 */
export async function enforceAccess(req: Request, res: Response, next: NextFunction): Promise<void> {
  // Read operations always allowed
  if (req.method === 'GET' || req.method === 'OPTIONS') {
    next();
    return;
  }

  const kb = extractKb(req);
  if (!kb) {
    // No KB context — let the route handler deal with validation
    next();
    return;
  }

  try {
    const kbMeta = await kbService.get(kb);
    if (!kbMeta) {
      // KB not found — let route handler return 404
      next();
      return;
    }

    if (kbMeta.access === 'read-only') {
      res.status(403).json({
        error: `Knowledge base "${kb}" is read-only. Modifications are not allowed.`,
      });
      return;
    }

    next();
  } catch {
    // On error, allow through — the route handler will validate further
    next();
  }
}
