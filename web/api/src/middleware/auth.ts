/**
 * Optional session token authentication.
 *
 * When ADJUTANT_WEB_SESSION_TOKEN is set (by Adjutant on startup), all API
 * requests must include a matching Bearer token in the Authorization header.
 * When not set, authentication is disabled (standalone / development mode).
 */

import type { Request, Response, NextFunction } from 'express';

const SESSION_TOKEN = process.env.ADJUTANT_WEB_SESSION_TOKEN || null;

if (SESSION_TOKEN) {
  console.log('Session token authentication enabled');
} else {
  console.log('Session token authentication disabled (ADJUTANT_WEB_SESSION_TOKEN not set)');
}

/**
 * Validate Bearer token against the session token.
 * Passes through if auth is disabled (no token configured).
 */
export function authenticate(req: Request, res: Response, next: NextFunction): void {
  // Auth disabled — allow all requests
  if (!SESSION_TOKEN) {
    next();
    return;
  }

  // Health check is always public
  if (req.path === '/health') {
    next();
    return;
  }

  const authHeader = req.headers.authorization;

  if (!authHeader) {
    res.status(401).json({ error: 'Authentication required. Provide Authorization: Bearer <token>' });
    return;
  }

  const parts = authHeader.split(' ');
  if (parts.length !== 2 || parts[0] !== 'Bearer' || parts[1] !== SESSION_TOKEN) {
    res.status(401).json({ error: 'Invalid session token' });
    return;
  }

  next();
}
