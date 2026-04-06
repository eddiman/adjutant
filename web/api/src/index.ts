import { createServer } from 'http';
import express from 'express';
import { config } from './config.js';
import { configService } from './services/configService.js';
import { kbService } from './services/kbService.js';
import { authenticate } from './middleware/auth.js';
import { enforceAccess } from './middleware/accessControl.js';
import { attachWebSocket } from './ws/index.js';
import configRouter from './routes/config.js';
import kbsRouter from './routes/kbs.js';
import foldersRouter from './routes/folders.js';
import notesRouter from './routes/notes.js';
import assetsRouter from './routes/assets.js';
import adjutantRouter from './routes/adjutant.js';
import explorerRouter from './routes/explorer.js';
import sessionsRouter from './routes/sessions.js';

export function createApp() {
  const app = express();

  // Middleware
  app.use(express.json());

  // CORS middleware — allow localhost and Tailscale origins
  app.use((req, res, next) => {
    const origin = req.headers.origin;

    if (origin) {
      try {
        const url = new URL(origin);
        const isLocalhost = url.hostname === 'localhost' || url.hostname === '127.0.0.1';
        const isTailscale = url.hostname.endsWith('.ts.net') || /^100\./.test(url.hostname);
        const isPrivate = /^(10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.)/.test(url.hostname);

        if (isLocalhost || isTailscale || isPrivate) {
          res.header('Access-Control-Allow-Origin', origin);
          res.header('Access-Control-Allow-Credentials', 'true');
        }
      } catch {
        // Malformed origin, skip
      }
    }

    res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
    res.header('Access-Control-Allow-Headers', 'Content-Type, Accept, Authorization');

    if (req.method === 'OPTIONS') {
      res.sendStatus(200);
      return;
    }
    next();
  });

  // Request logging
  app.use((req, _res, next) => {
    console.log(`${new Date().toISOString()} ${req.method} ${req.path}`);
    next();
  });

  // Authentication (optional — enabled when ADJUTANT_WEB_SESSION_TOKEN is set)
  app.use('/api', authenticate);

  // Access control (block writes to read-only KBs)
  app.use('/api/notes', enforceAccess);
  app.use('/api/folders', enforceAccess);
  app.use('/api/assets', enforceAccess);

  // Routes
  app.use('/api/config', configRouter);
  app.use('/api/kbs', kbsRouter);
  app.use('/api/folders', foldersRouter);
  app.use('/api/notes', notesRouter);
  app.use('/api/assets', assetsRouter);
  app.use('/api/adjutant', adjutantRouter);
  app.use('/api/explorer', explorerRouter);
  app.use('/api/sessions', sessionsRouter);

  // Health check
  app.get('/health', (_req, res) => {
    res.json({ status: 'ok', timestamp: new Date().toISOString() });
  });

  // 404 handler
  app.use((_req, res) => {
    res.status(404).json({ error: 'Not found' });
  });

  // Error handler
  app.use((err: Error, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
    console.error('Unhandled error:', err);
    res.status(500).json({ error: 'Internal server error' });
  });

  return app;
}

// Start server
async function start() {
  try {
    await configService.init();

    const app = createApp();
    const server = createServer(app);
    attachWebSocket(server);

    server.listen(config.port, config.host, async () => {
      const mode = await kbService.getMode();
      const kbRoot = await configService.getKbRoot();
      const kbs = await kbService.list();

      console.log(`Adjutant Web running on http://${config.host}:${config.port}`);
      console.log(`Mode: ${mode}`);
      if (mode === 'adjutant') {
        console.log(`Adjutant integration active — ${kbs.length} KBs from registry`);
      } else {
        console.log(`KB root: ${kbRoot || '(not configured — set via /api/config)'}`);
      }
    });
  } catch (error) {
    console.error('Failed to start server:', error);
    process.exit(1);
  }
}

// Only start the server when this file is executed directly (not imported for testing)
const isDirectExecution = process.argv[1] && (
  process.argv[1].endsWith('/index.ts') ||
  process.argv[1].endsWith('/index.js')
);

if (isDirectExecution) {
  start();
}
