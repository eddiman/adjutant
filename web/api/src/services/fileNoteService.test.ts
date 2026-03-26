import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import fs from 'fs/promises';
import path from 'path';
import os from 'os';
import { fileNoteService } from './fileNoteService.js';
import { folderService } from './folderService.js';
import { configService } from './configService.js';
import { registryService } from './registryService.js';
import { config } from '../config.js';

let tempDir: string;
let kbRoot: string;
let originalHome: string | undefined;

beforeEach(async () => {
  tempDir = await fs.mkdtemp(path.join(os.tmpdir(), 'adjutant-web-test-note-'));
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

  await fs.writeFile(
    path.join(tempDir, 'config.json'),
    JSON.stringify({ kbRoot }),
    'utf-8',
  );
  configService.clearCache();
});

afterEach(async () => {
  process.env.HOME = originalHome;
  registryService.clearCache();
  await fs.rm(tempDir, { recursive: true, force: true });
});

async function createTestKb(name: string) {
  const kbDir = path.join(kbRoot, name);
  await fs.mkdir(kbDir, { recursive: true });
  await fs.writeFile(
    path.join(kbDir, 'kb.yaml'),
    `name: ${name}\ndescription: Test\n`,
    'utf-8',
  );
  return kbDir;
}

describe('FileNoteService', () => {
  describe('get', () => {
    it('reads a markdown file and extracts title from heading', async () => {
      const kbDir = await createTestKb('test-kb');
      await fs.writeFile(
        path.join(kbDir, 'hello.md'),
        '# Hello World\n\nSome content here.',
        'utf-8',
      );

      const note = await fileNoteService.get('test-kb', 'hello.md');
      expect(note).not.toBeNull();
      expect(note!.filename).toBe('hello.md');
      expect(note!.path).toBe('hello.md');
      expect(note!.kb).toBe('test-kb');
      expect(note!.title).toBe('Hello World');
      expect(note!.content).toContain('Some content here.');
      expect(note!.size).toBeGreaterThan(0);
    });

    it('falls back to filename when no heading found', async () => {
      const kbDir = await createTestKb('test-kb');
      await fs.writeFile(
        path.join(kbDir, 'no-heading.md'),
        'Just some text without a heading.',
        'utf-8',
      );

      const note = await fileNoteService.get('test-kb', 'no-heading.md');
      expect(note!.title).toBe('no-heading');
    });

    it('uses title from .adjutant-web.json when available', async () => {
      const kbDir = await createTestKb('test-kb');
      await fs.writeFile(path.join(kbDir, 'doc.md'), '# Original Title', 'utf-8');

      // Set a custom title in sidecar
      await folderService.updateMeta('test-kb', '', {
        items: { 'doc.md': { title: 'Custom Title' } },
      });

      const note = await fileNoteService.get('test-kb', 'doc.md');
      expect(note!.title).toBe('Custom Title');
    });

    it('reads notes in subdirectories', async () => {
      const kbDir = await createTestKb('test-kb');
      await fs.mkdir(path.join(kbDir, 'data'));
      await fs.writeFile(
        path.join(kbDir, 'data', 'current.md'),
        '# Current Status\n\nAll good.',
        'utf-8',
      );

      const note = await fileNoteService.get('test-kb', 'data/current.md');
      expect(note).not.toBeNull();
      expect(note!.filename).toBe('current.md');
      expect(note!.path).toBe(path.join('data', 'current.md'));
      expect(note!.title).toBe('Current Status');
    });

    it('includes tags and position from sidecar', async () => {
      const kbDir = await createTestKb('test-kb');
      await fs.writeFile(path.join(kbDir, 'tagged.md'), '# Tagged', 'utf-8');

      await folderService.updateMeta('test-kb', '', {
        items: {
          'tagged.md': {
            tags: ['important', 'urgent'],
            position: { x: 50, y: 75 },
          },
        },
      });

      const note = await fileNoteService.get('test-kb', 'tagged.md');
      expect(note!.tags).toEqual(['important', 'urgent']);
      expect(note!.position).toEqual({ x: 50, y: 75 });
    });

    it('returns null for nonexistent file', async () => {
      await createTestKb('test-kb');
      const note = await fileNoteService.get('test-kb', 'nonexistent.md');
      expect(note).toBeNull();
    });

    it('prevents path traversal', async () => {
      await createTestKb('test-kb');
      const note = await fileNoteService.get('test-kb', '../../../etc/passwd');
      expect(note).toBeNull();
    });
  });

  describe('search', () => {
    it('finds notes by filename match', async () => {
      const kbDir = await createTestKb('test-kb');
      await fs.writeFile(path.join(kbDir, 'meeting-notes.md'), '# Meeting', 'utf-8');
      await fs.writeFile(path.join(kbDir, 'readme.md'), '# Readme', 'utf-8');

      const results = await fileNoteService.search('test-kb', 'meeting');
      expect(results).toHaveLength(1);
      expect(results[0].filename).toBe('meeting-notes.md');
    });

    it('finds notes by content match', async () => {
      const kbDir = await createTestKb('test-kb');
      await fs.writeFile(path.join(kbDir, 'alpha.md'), '# Alpha\n\nContains keyword secret.', 'utf-8');
      await fs.writeFile(path.join(kbDir, 'beta.md'), '# Beta\n\nNothing special.', 'utf-8');

      const results = await fileNoteService.search('test-kb', 'secret');
      expect(results).toHaveLength(1);
      expect(results[0].filename).toBe('alpha.md');
    });

    it('searches recursively through subdirectories', async () => {
      const kbDir = await createTestKb('test-kb');
      await fs.mkdir(path.join(kbDir, 'data'));
      await fs.mkdir(path.join(kbDir, 'data', 'nested'));
      await fs.writeFile(
        path.join(kbDir, 'data', 'nested', 'deep.md'),
        '# Deep Note\n\nBuried content here.',
        'utf-8',
      );

      const results = await fileNoteService.search('test-kb', 'buried');
      expect(results).toHaveLength(1);
      expect(results[0].path).toBe(path.join('data', 'nested', 'deep.md'));
    });

    it('returns empty array for no matches', async () => {
      const kbDir = await createTestKb('test-kb');
      await fs.writeFile(path.join(kbDir, 'note.md'), '# Note', 'utf-8');

      const results = await fileNoteService.search('test-kb', 'zzzznotfound');
      expect(results).toEqual([]);
    });

    it('searches case-insensitively', async () => {
      const kbDir = await createTestKb('test-kb');
      await fs.writeFile(path.join(kbDir, 'doc.md'), '# Document\n\nImportant DATA here.', 'utf-8');

      const results = await fileNoteService.search('test-kb', 'data');
      expect(results).toHaveLength(1);
    });

    it('only searches .md files', async () => {
      const kbDir = await createTestKb('test-kb');
      await fs.writeFile(path.join(kbDir, 'data.json'), '{"query": "findme"}', 'utf-8');
      await fs.writeFile(path.join(kbDir, 'findme.md'), '# Found', 'utf-8');

      const results = await fileNoteService.search('test-kb', 'findme');
      expect(results).toHaveLength(1);
      expect(results[0].filename).toBe('findme.md');
    });
  });

  describe('create', () => {
    it('creates a new note file in KB root', async () => {
      await createTestKb('test-kb');

      const note = await fileNoteService.create({
        kb: 'test-kb',
        title: 'My New Note',
        content: '',
        folder: '',
      });

      expect(note).not.toBeNull();
      expect(note!.filename).toBe('my-new-note.md');
      expect(note!.kb).toBe('test-kb');
      expect(note!.title).toBe('My New Note');
      expect(note!.content).toContain('# My New Note');

      // Verify file was actually written
      const kbDir = path.join(kbRoot, 'test-kb');
      const fileStat = await fs.stat(path.join(kbDir, 'my-new-note.md'));
      expect(fileStat.isFile()).toBe(true);
    });

    it('creates a note in a subfolder', async () => {
      const kbDir = await createTestKb('test-kb');
      await fs.mkdir(path.join(kbDir, 'data'));

      const note = await fileNoteService.create({
        kb: 'test-kb',
        title: 'Sub Note',
        folder: 'data',
      });

      expect(note).not.toBeNull();
      expect(note!.path).toBe(path.join('data', 'sub-note.md'));
    });

    it('auto-deduplicates filenames', async () => {
      const kbDir = await createTestKb('test-kb');
      await fs.writeFile(path.join(kbDir, 'my-note.md'), '# Existing', 'utf-8');

      const note = await fileNoteService.create({
        kb: 'test-kb',
        title: 'My Note',
      });

      expect(note).not.toBeNull();
      expect(note!.filename).toBe('my-note-2.md');
    });

    it('stores tags and position in sidecar metadata', async () => {
      await createTestKb('test-kb');

      const note = await fileNoteService.create({
        kb: 'test-kb',
        title: 'Tagged Note',
        tags: ['important'],
        position: { x: 100, y: 200 },
      });

      expect(note).not.toBeNull();
      expect(note!.tags).toEqual(['important']);
      expect(note!.position).toEqual({ x: 100, y: 200 });

      // Verify metadata in .adjutant-web.json
      const meta = await folderService.getMeta('test-kb', '');
      expect(meta!.items['tagged-note.md']).toBeDefined();
      expect(meta!.items['tagged-note.md'].tags).toEqual(['important']);
    });

    it('returns null for nonexistent KB', async () => {
      const note = await fileNoteService.create({
        kb: 'nonexistent',
        title: 'Test',
      });
      expect(note).toBeNull();
    });

    it('uses provided filename if given', async () => {
      await createTestKb('test-kb');

      const note = await fileNoteService.create({
        kb: 'test-kb',
        title: 'Custom',
        filename: 'custom-name.md',
      });

      expect(note).not.toBeNull();
      expect(note!.filename).toBe('custom-name.md');
    });

    it('does not double-add # heading if content already has one', async () => {
      await createTestKb('test-kb');

      const note = await fileNoteService.create({
        kb: 'test-kb',
        title: 'Test',
        content: '# Test\n\nBody here.',
      });

      expect(note).not.toBeNull();
      // Should NOT have "# Test\n\n# Test\n\nBody here."
      const headingCount = (note!.content.match(/^# /gm) || []).length;
      expect(headingCount).toBe(1);
    });
  });

  describe('update', () => {
    it('updates note content', async () => {
      const kbDir = await createTestKb('test-kb');
      await fs.writeFile(path.join(kbDir, 'doc.md'), '# Original', 'utf-8');

      const updated = await fileNoteService.update('test-kb', 'doc.md', {
        content: '# Updated\n\nNew content.',
      });

      expect(updated).not.toBeNull();
      expect(updated!.content).toContain('New content.');

      // Verify file was actually written
      const fileContent = await fs.readFile(path.join(kbDir, 'doc.md'), 'utf-8');
      expect(fileContent).toContain('New content.');
    });

    it('updates metadata without changing content', async () => {
      const kbDir = await createTestKb('test-kb');
      await fs.writeFile(path.join(kbDir, 'doc.md'), '# Doc', 'utf-8');

      const updated = await fileNoteService.update('test-kb', 'doc.md', {
        title: 'Renamed Doc',
        tags: ['updated'],
      });

      expect(updated).not.toBeNull();
      expect(updated!.title).toBe('Renamed Doc');
      expect(updated!.tags).toEqual(['updated']);
      // Content should be unchanged
      const fileContent = await fs.readFile(path.join(kbDir, 'doc.md'), 'utf-8');
      expect(fileContent).toBe('# Doc');
    });

    it('returns null for nonexistent note', async () => {
      await createTestKb('test-kb');
      const result = await fileNoteService.update('test-kb', 'nope.md', { content: 'x' });
      expect(result).toBeNull();
    });

    it('prevents path traversal', async () => {
      await createTestKb('test-kb');
      const result = await fileNoteService.update('test-kb', '../../../etc/passwd', { content: 'x' });
      expect(result).toBeNull();
    });
  });

  describe('delete', () => {
    it('deletes a note file', async () => {
      const kbDir = await createTestKb('test-kb');
      await fs.writeFile(path.join(kbDir, 'to-delete.md'), '# Delete me', 'utf-8');

      const result = await fileNoteService.delete('test-kb', 'to-delete.md');
      expect(result).toBe(true);

      // Verify file is gone
      await expect(fs.access(path.join(kbDir, 'to-delete.md'))).rejects.toThrow();
    });

    it('cleans up sidecar metadata on delete', async () => {
      const kbDir = await createTestKb('test-kb');
      await fs.writeFile(path.join(kbDir, 'tracked.md'), '# Tracked', 'utf-8');

      // Add metadata
      await folderService.updateMeta('test-kb', '', {
        items: { 'tracked.md': { position: { x: 10, y: 20 }, tags: ['tag1'] } },
      });

      await fileNoteService.delete('test-kb', 'tracked.md');

      const meta = await folderService.getMeta('test-kb', '');
      expect(meta!.items['tracked.md']).toBeUndefined();
    });

    it('returns false for nonexistent note', async () => {
      await createTestKb('test-kb');
      const result = await fileNoteService.delete('test-kb', 'nope.md');
      expect(result).toBe(false);
    });

    it('prevents path traversal', async () => {
      await createTestKb('test-kb');
      const result = await fileNoteService.delete('test-kb', '../../../etc/passwd');
      expect(result).toBe(false);
    });
  });

  describe('extractTitle', () => {
    it('extracts title from # heading', () => {
      expect(fileNoteService.extractTitle('# Hello World', 'file.md')).toBe('Hello World');
    });

    it('extracts title from heading with extra spaces', () => {
      expect(fileNoteService.extractTitle('#   Spaced Title  ', 'file.md')).toBe('Spaced Title');
    });

    it('extracts first heading from multiple headings', () => {
      const content = '# First\n\n## Second\n\n# Third';
      expect(fileNoteService.extractTitle(content, 'file.md')).toBe('First');
    });

    it('falls back to filename sans extension', () => {
      expect(fileNoteService.extractTitle('No heading here', 'my-document.md')).toBe('my-document');
    });

    it('handles heading after blank lines', () => {
      const content = '\n\n# After Blanks';
      expect(fileNoteService.extractTitle(content, 'file.md')).toBe('After Blanks');
    });
  });

  describe('concurrency', () => {
    it('creates unique filenames for 10 concurrent notes with the same title', async () => {
      await createTestKb('test-kb');

      const promises = Array.from({ length: 10 }, () =>
        fileNoteService.create({ kb: 'test-kb', title: 'Concurrent Note', folder: '' }),
      );
      const results = await Promise.all(promises);

      const filenames = results.filter(Boolean).map(r => r!.filename);
      const uniqueFilenames = new Set(filenames);
      expect(uniqueFilenames.size).toBe(10);
    });

    it('creates unique filenames for rapid sequential notes', async () => {
      await createTestKb('test-kb');

      const results = [];
      for (let i = 0; i < 5; i++) {
        results.push(await fileNoteService.create({ kb: 'test-kb', title: 'Rapid', folder: '' }));
      }

      const filenames = results.filter(Boolean).map(r => r!.filename);
      const uniqueFilenames = new Set(filenames);
      expect(uniqueFilenames.size).toBe(5);
    });
  });
});
