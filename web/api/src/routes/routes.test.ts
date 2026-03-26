import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import request from 'supertest';
import fs from 'fs/promises';
import path from 'path';
import os from 'os';
import { createApp } from '../index.js';
import { configService } from '../services/configService.js';
import { registryService } from '../services/registryService.js';
import { config } from '../config.js';

let tempDir: string;
let kbRoot: string;
let app: ReturnType<typeof createApp>;
let originalHome: string | undefined;

beforeEach(async () => {
  tempDir = await fs.mkdtemp(path.join(os.tmpdir(), 'adjutant-web-test-routes-'));
  kbRoot = path.join(tempDir, 'kbs');
  await fs.mkdir(kbRoot);

  originalHome = process.env.HOME;
  process.env.HOME = tempDir;
  delete process.env.ADJUTANT_DIR;
  delete process.env.ADJ_DIR;
  registryService.clearCache();

  Object.defineProperty(config, 'configDir', { value: tempDir, writable: true, configurable: true });
  Object.defineProperty(config, 'configFile', {
    get: () => path.join(tempDir, 'config.json'),
    configurable: true,
  });

  // Create a test KB
  const kbDir = path.join(kbRoot, 'test-kb');
  await fs.mkdir(kbDir);
  await fs.writeFile(
    path.join(kbDir, 'kb.yaml'),
    'name: test-kb\ndescription: A test KB\naccess: read-write\n',
    'utf-8',
  );
  await fs.mkdir(path.join(kbDir, 'data'));
  await fs.writeFile(
    path.join(kbDir, 'data', 'current.md'),
    '# Current Status\n\nEverything is working.',
    'utf-8',
  );
  await fs.writeFile(
    path.join(kbDir, 'README.md'),
    '# Test KB\n\nThis is the readme.',
    'utf-8',
  );

  // Write config pointing to kbRoot
  await fs.writeFile(
    path.join(tempDir, 'config.json'),
    JSON.stringify({ kbRoot }),
    'utf-8',
  );
  configService.clearCache();

  app = createApp();
});

afterEach(async () => {
  process.env.HOME = originalHome;
  registryService.clearCache();
  await fs.rm(tempDir, { recursive: true, force: true });
});

describe('Health', () => {
  it('GET /health returns ok', async () => {
    const res = await request(app).get('/health');
    expect(res.status).toBe(200);
    expect(res.body.status).toBe('ok');
  });
});

describe('Config routes', () => {
  it('GET /api/config returns current config', async () => {
    const res = await request(app).get('/api/config');
    expect(res.status).toBe(200);
    expect(res.body.kbRoot).toBe(kbRoot);
  });
});

describe('KB routes', () => {
  it('GET /api/kbs lists discovered KBs', async () => {
    const res = await request(app).get('/api/kbs');
    expect(res.status).toBe(200);
    expect(res.body.kbs).toHaveLength(1);
    expect(res.body.kbs[0].name).toBe('test-kb');
    expect(res.body.kbs[0].description).toBe('A test KB');
  });

  it('GET /api/kbs/:name returns a single KB', async () => {
    const res = await request(app).get('/api/kbs/test-kb');
    expect(res.status).toBe(200);
    expect(res.body.name).toBe('test-kb');
  });

  it('GET /api/kbs/:name returns 404 for missing KB', async () => {
    const res = await request(app).get('/api/kbs/nonexistent');
    expect(res.status).toBe(404);
  });
});

describe('Folder routes', () => {
  it('GET /api/folders lists KB root', async () => {
    const res = await request(app).get('/api/folders').query({ kb: 'test-kb' });
    expect(res.status).toBe(200);
    expect(res.body.kb).toBe('test-kb');
    expect(res.body.entries.length).toBeGreaterThan(0);

    const names = res.body.entries.map((e: { name: string }) => e.name);
    expect(names).toContain('data');
    expect(names).toContain('README.md');
  });

  it('GET /api/folders lists subfolder', async () => {
    const res = await request(app).get('/api/folders').query({ kb: 'test-kb', path: 'data' });
    expect(res.status).toBe(200);
    expect(res.body.path).toBe('data');
    expect(res.body.entries.some((e: { name: string }) => e.name === 'current.md')).toBe(true);
  });

  it('GET /api/folders returns 400 without kb param', async () => {
    const res = await request(app).get('/api/folders');
    expect(res.status).toBe(400);
  });

  it('GET /api/folders/meta returns default sidecar', async () => {
    const res = await request(app).get('/api/folders/meta').query({ kb: 'test-kb' });
    expect(res.status).toBe(200);
    expect(res.body.items).toEqual({});
    expect(res.body.sections).toEqual({});
  });

  it('PUT /api/folders/meta updates sidecar', async () => {
    const res = await request(app)
      .put('/api/folders/meta')
      .query({ kb: 'test-kb' })
      .send({ items: { 'README.md': { position: { x: 10, y: 20 } } } });

    expect(res.status).toBe(200);
    expect(res.body.items['README.md'].position).toEqual({ x: 10, y: 20 });
  });

  it('POST /api/folders/sections creates a section', async () => {
    const res = await request(app)
      .post('/api/folders/sections')
      .query({ kb: 'test-kb' })
      .send({ name: 'My Section', color: 'blue' });

    expect(res.status).toBe(201);
    expect(res.body.id).toMatch(/^section-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);
    expect(res.body.section.name).toBe('My Section');
  });

  it('DELETE /api/folders/sections deletes a section', async () => {
    // Create first
    const createRes = await request(app)
      .post('/api/folders/sections')
      .query({ kb: 'test-kb' })
      .send({ name: 'Delete Me' });
    
    const sectionId = createRes.body.id;

    const res = await request(app)
      .delete('/api/folders/sections')
      .query({ kb: 'test-kb', id: sectionId });

    expect(res.status).toBe(204);
  });

  it('POST /api/folders/stickies creates a sticky', async () => {
    const res = await request(app)
      .post('/api/folders/stickies')
      .query({ kb: 'test-kb' })
      .send({ text: 'Remember this', color: 'pink' });

    expect(res.status).toBe(201);
    expect(res.body.id).toMatch(/^sticky-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);
    expect(res.body.sticky.text).toBe('Remember this');
  });
});

describe('Note routes', () => {
  it('GET /api/notes returns a note', async () => {
    const res = await request(app)
      .get('/api/notes')
      .query({ kb: 'test-kb', path: 'data/current.md' });

    expect(res.status).toBe(200);
    expect(res.body.filename).toBe('current.md');
    expect(res.body.title).toBe('Current Status');
    expect(res.body.content).toContain('Everything is working.');
  });

  it('GET /api/notes returns 404 for missing note', async () => {
    const res = await request(app)
      .get('/api/notes')
      .query({ kb: 'test-kb', path: 'nonexistent.md' });

    expect(res.status).toBe(404);
  });

  it('GET /api/notes returns 400 without required params', async () => {
    const res = await request(app).get('/api/notes');
    expect(res.status).toBe(400);
  });

  it('GET /api/notes/search finds notes by content', async () => {
    const res = await request(app)
      .get('/api/notes/search')
      .query({ kb: 'test-kb', q: 'working' });

    expect(res.status).toBe(200);
    expect(res.body.notes.length).toBeGreaterThan(0);
    expect(res.body.notes[0].filename).toBe('current.md');
  });

  it('GET /api/notes/search returns empty for no matches', async () => {
    const res = await request(app)
      .get('/api/notes/search')
      .query({ kb: 'test-kb', q: 'zzzznotfound' });

    expect(res.status).toBe(200);
    expect(res.body.notes).toEqual([]);
  });

  it('POST /api/notes creates a new note', async () => {
    const res = await request(app)
      .post('/api/notes')
      .send({
        kb: 'test-kb',
        title: 'Brand New Note',
        content: '',
        folder: 'data',
        tags: ['test'],
        position: { x: 50, y: 100 },
      });

    expect(res.status).toBe(201);
    expect(res.body.filename).toBe('brand-new-note.md');
    expect(res.body.kb).toBe('test-kb');
    expect(res.body.title).toBe('Brand New Note');
    expect(res.body.tags).toEqual(['test']);
    expect(res.body.position).toEqual({ x: 50, y: 100 });
  });

  it('POST /api/notes returns 400 for missing title', async () => {
    const res = await request(app)
      .post('/api/notes')
      .send({ kb: 'test-kb' });

    expect(res.status).toBe(400);
  });

  it('PUT /api/notes updates a note', async () => {
    const res = await request(app)
      .put('/api/notes')
      .query({ kb: 'test-kb', path: 'data/current.md' })
      .send({ content: '# Updated Status\n\nAll updated.' });

    expect(res.status).toBe(200);
    expect(res.body.content).toContain('All updated.');
  });

  it('PUT /api/notes returns 404 for missing note', async () => {
    const res = await request(app)
      .put('/api/notes')
      .query({ kb: 'test-kb', path: 'nope.md' })
      .send({ content: 'x' });

    expect(res.status).toBe(404);
  });

  it('DELETE /api/notes deletes a note', async () => {
    // Create a note to delete
    await request(app)
      .post('/api/notes')
      .send({ kb: 'test-kb', title: 'Delete Me', folder: '' });

    const res = await request(app)
      .delete('/api/notes')
      .query({ kb: 'test-kb', path: 'delete-me.md' });

    expect(res.status).toBe(204);

    // Verify it's gone
    const getRes = await request(app)
      .get('/api/notes')
      .query({ kb: 'test-kb', path: 'delete-me.md' });

    expect(getRes.status).toBe(404);
  });
});

describe('404 handler', () => {
  it('returns 404 for unknown routes', async () => {
    const res = await request(app).get('/api/unknown');
    expect(res.status).toBe(404);
  });
});
