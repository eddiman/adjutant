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

describe('Session routes — CLI discovery', () => {
  it('GET /api/sessions extracts real cwd from JSONL (handles underscores/dashes)', async () => {
    // The Claude CLI encoding `-Volumes-Mandalor-knowledge-bases-my-kb`
    // cannot be losslessly decoded — the true cwd may include underscores
    // (e.g. `knowledge_bases`) that the decoder would have flattened to `/`.
    // scanClaudeCliSessions must pull the real cwd from the JSONL records
    // themselves, not from the directory name.
    const encodedDir = '-Volumes-Mandalor-knowledge-bases-my-kb';
    const realCwd = '/Volumes/Mandalor/knowledge_bases/my-kb';
    const sessionId = '11111111-2222-3333-4444-555555555555';

    const projDir = path.join(tempDir, '.claude', 'projects', encodedDir);
    await fs.mkdir(projDir, { recursive: true });

    const jsonl = [
      JSON.stringify({
        type: 'user',
        uuid: 'u1',
        cwd: realCwd,
        timestamp: '2026-04-09T10:00:00Z',
        message: { content: [{ type: 'text', text: 'Hello KB' }] },
      }),
      JSON.stringify({
        type: 'assistant',
        uuid: 'a1',
        timestamp: '2026-04-09T10:00:01Z',
        message: { model: 'claude-sonnet-4-6', content: [{ type: 'text', text: 'Hi' }] },
      }),
    ].join('\n');

    await fs.writeFile(path.join(projDir, `${sessionId}.jsonl`), jsonl);

    const res = await request(app).get('/api/sessions');
    expect(res.status).toBe(200);
    const match = res.body.cliSessions.find((s: { id: string }) => s.id === sessionId);
    expect(match).toBeDefined();
    expect(match.cwd).toBe(realCwd);
    expect(match.name).toBe('Hello KB');
  });

  it('GET /api/sessions extracts preview from string content (not just array content)', async () => {
    // The Claude CLI writes user records with `content` as either a
    // plain string or an array of content blocks. Previously only the
    // array case was handled, so every string-content session (the
    // common case) showed up as "Untitled session".
    const encodedDir = '-tmp-adj-test-string-content';
    const realCwd = '/tmp/adj-test-string-content';
    const sessionId = '33333333-2222-3333-4444-555555555555';

    const projDir = path.join(tempDir, '.claude', 'projects', encodedDir);
    await fs.mkdir(projDir, { recursive: true });

    const jsonl = [
      JSON.stringify({
        type: 'user',
        uuid: 'u1',
        cwd: realCwd,
        timestamp: '2026-04-09T10:00:00Z',
        message: { content: 'Apply the following updates:\n\n1. Do a thing' },
      }),
    ].join('\n');

    await fs.writeFile(path.join(projDir, `${sessionId}.jsonl`), jsonl);

    const res = await request(app).get('/api/sessions');
    expect(res.status).toBe(200);
    const match = res.body.cliSessions.find((s: { id: string }) => s.id === sessionId);
    expect(match).toBeDefined();
    // Newlines and runs of whitespace should be collapsed to a single space.
    expect(match.name).toBe('Apply the following updates: 1. Do a thing');
  });

  it('GET /api/sessions discovers nested sub-agent sessions and uses meta.json title', async () => {
    // Claude CLI stores sub-agent session logs at:
    //   <projectDir>/<parent-uuid>/subagents/agent-<hash>.jsonl
    // with a sibling agent-<hash>.meta.json. These were previously not
    // scanned at all (the scan only looked at top-level .jsonl files),
    // so sub-agent sessions were invisible in the list.
    const encodedDir = '-tmp-adj-test-subagents';
    const realCwd = '/tmp/adj-test-subagents';
    const parentId = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee';
    const agentId = 'agent-1234567890abcdef';

    const subagentsDir = path.join(tempDir, '.claude', 'projects', encodedDir, parentId, 'subagents');
    await fs.mkdir(subagentsDir, { recursive: true });

    // Sub-agent JSONL — every record is sidechain by design.
    const jsonl = [
      JSON.stringify({
        type: 'user',
        uuid: 'su1',
        cwd: realCwd,
        isSidechain: true,
        timestamp: '2026-04-09T11:00:00Z',
        message: { content: 'Do the thing' },
      }),
    ].join('\n');
    await fs.writeFile(path.join(subagentsDir, `${agentId}.jsonl`), jsonl);

    // Sibling meta.json with a human description.
    await fs.writeFile(
      path.join(subagentsDir, `${agentId}.meta.json`),
      JSON.stringify({ agentType: 'claude-code-guide', description: 'Remote session clearing' }),
    );

    const res = await request(app).get('/api/sessions');
    expect(res.status).toBe(200);
    const match = res.body.cliSessions.find((s: { id: string }) => s.id === agentId);
    expect(match).toBeDefined();
    // Title should come from the meta.json, not the sidechain user text.
    expect(match.name).toBe('claude-code-guide · Remote session clearing');
    expect(match.cwd).toBe(realCwd);
  });

  it('GET /api/sessions falls back to sidechain text when no meta and no non-sidechain record exists', async () => {
    // Sub-agent files without a meta.json should still get a title from
    // their sidechain user record (second-pass fallback), rather than
    // showing "Untitled session".
    const encodedDir = '-tmp-adj-test-subagents-nometa';
    const realCwd = '/tmp/adj-test-subagents-nometa';
    const parentId = 'ffffffff-bbbb-cccc-dddd-eeeeeeeeeeee';
    const agentId = 'agent-deadbeef12345678';

    const subagentsDir = path.join(tempDir, '.claude', 'projects', encodedDir, parentId, 'subagents');
    await fs.mkdir(subagentsDir, { recursive: true });

    const jsonl = [
      JSON.stringify({
        type: 'user',
        uuid: 'su1',
        cwd: realCwd,
        isSidechain: true,
        timestamp: '2026-04-09T11:00:00Z',
        message: { content: 'Analyze the production logs' },
      }),
    ].join('\n');
    await fs.writeFile(path.join(subagentsDir, `${agentId}.jsonl`), jsonl);

    const res = await request(app).get('/api/sessions');
    const match = res.body.cliSessions.find((s: { id: string }) => s.id === agentId);
    expect(match).toBeDefined();
    expect(match.name).toBe('Analyze the production logs');
  });

  it('GET /api/sessions skips sidechain user records when picking preview', async () => {
    const encodedDir = '-tmp-adj-test-sidechain';
    const realCwd = '/tmp/adj-test-sidechain';
    const sessionId = '22222222-2222-3333-4444-555555555555';

    const projDir = path.join(tempDir, '.claude', 'projects', encodedDir);
    await fs.mkdir(projDir, { recursive: true });

    const jsonl = [
      // Sidechain (sub-agent) user message — must be ignored for preview.
      JSON.stringify({
        type: 'user',
        uuid: 'u-side',
        cwd: realCwd,
        isSidechain: true,
        timestamp: '2026-04-09T10:00:00Z',
        message: { content: [{ type: 'text', text: 'SIDECHAIN PROMPT' }] },
      }),
      // Real user message — should be used for preview.
      JSON.stringify({
        type: 'user',
        uuid: 'u-real',
        cwd: realCwd,
        timestamp: '2026-04-09T10:00:01Z',
        message: { content: [{ type: 'text', text: 'Real parent prompt' }] },
      }),
    ].join('\n');

    await fs.writeFile(path.join(projDir, `${sessionId}.jsonl`), jsonl);

    const res = await request(app).get('/api/sessions');
    const match = res.body.cliSessions.find((s: { id: string }) => s.id === sessionId);
    expect(match).toBeDefined();
    expect(match.name).toBe('Real parent prompt');
  });
});

describe('404 handler', () => {
  it('returns 404 for unknown routes', async () => {
    const res = await request(app).get('/api/unknown');
    expect(res.status).toBe(404);
  });
});
