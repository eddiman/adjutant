/**
 * WebSocket server for code sessions.
 *
 * Attaches to the HTTP server at /ws/code-session path.
 * Auth is handled during the HTTP upgrade event — if ADJUTANT_WEB_SESSION_TOKEN
 * is set, the client must pass ?token=xxx in the WebSocket URL.
 */

import { WebSocketServer, type WebSocket } from 'ws';
import type { Server, IncomingMessage } from 'http';
import { handleConnection } from './sessionHandler.js';

const SESSION_TOKEN = process.env.ADJUTANT_WEB_SESSION_TOKEN || null;

export function attachWebSocket(server: Server): WebSocketServer {
  const wss = new WebSocketServer({ noServer: true });

  server.on('upgrade', (request: IncomingMessage, socket, head) => {
    const url = new URL(request.url || '', `http://${request.headers.host || 'localhost'}`);

    if (url.pathname !== '/ws/code-session') {
      socket.destroy();
      return;
    }

    // Authenticate if token is configured
    if (SESSION_TOKEN) {
      const token = url.searchParams.get('token');
      if (token !== SESSION_TOKEN) {
        socket.write('HTTP/1.1 401 Unauthorized\r\n\r\n');
        socket.destroy();
        return;
      }
    }

    wss.handleUpgrade(request, socket, head, (ws: WebSocket) => {
      wss.emit('connection', ws, request);
    });
  });

  wss.on('connection', (ws: WebSocket) => {
    handleConnection(ws);
  });

  return wss;
}
