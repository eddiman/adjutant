import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import fs from 'fs/promises';
import path from 'path';
import os from 'os';
import { kbService } from './kbService.js';
import { configService } from './configService.js';
import { registryService } from './registryService.js';
import { config } from '../config.js';

let tempDir: string;
let kbRoot: string;
let originalHome: string | undefined;

beforeEach(async () => {
  tempDir = await fs.mkdtemp(path.join(os.tmpdir(), 'adjutant-web-test-kb-'));
  kbRoot = path.join(tempDir, 'kbs');
  await fs.mkdir(kbRoot);

  // Prevent registryService from finding real ~/.adjutant
  originalHome = process.env.HOME;
  process.env.HOME = tempDir;
  delete process.env.ADJUTANT_DIR;
  delete process.env.ADJ_DIR;
  registryService.clearCache();

  // Patch config to use temp dir
  Object.defineProperty(config, 'configDir', { value: tempDir, writable: true, configurable: true });
  Object.defineProperty(config, 'configFile', {
    get: () => path.join(tempDir, 'config.json'),
    configurable: true,
  });

  // Write a config with kbRoot pointing to our test dir
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

async function createTestKb(name: string, yamlContent: string) {
  const kbDir = path.join(kbRoot, name);
  await fs.mkdir(kbDir, { recursive: true });
  await fs.writeFile(path.join(kbDir, 'kb.yaml'), yamlContent, 'utf-8');
}

describe('KbService', () => {
  it('returns empty list when kbRoot has no KBs', async () => {
    const kbs = await kbService.list();
    expect(kbs).toEqual([]);
  });

  it('discovers KBs with kb.yaml files', async () => {
    await createTestKb('alpha', 'name: alpha\ndescription: Alpha KB\naccess: read-only\ncreated: "2026-01-01"\n');
    await createTestKb('beta', 'name: beta\ndescription: Beta KB\naccess: read-write\n');

    const kbs = await kbService.list();
    expect(kbs).toHaveLength(2);
    expect(kbs[0].name).toBe('alpha');
    expect(kbs[0].description).toBe('Alpha KB');
    expect(kbs[0].access).toBe('read-only');
    expect(kbs[0].created).toBe('2026-01-01');
    expect(kbs[1].name).toBe('beta');
    expect(kbs[1].access).toBe('read-write');
  });

  it('ignores directories without kb.yaml', async () => {
    await createTestKb('valid', 'name: valid\ndescription: Valid\n');
    const noYaml = path.join(kbRoot, 'invalid');
    await fs.mkdir(noYaml);
    await fs.writeFile(path.join(noYaml, 'README.md'), '# No kb.yaml here', 'utf-8');

    const kbs = await kbService.list();
    expect(kbs).toHaveLength(1);
    expect(kbs[0].name).toBe('valid');
  });

  it('ignores hidden directories', async () => {
    await createTestKb('.hidden-kb', 'name: hidden\ndescription: Hidden\n');
    await createTestKb('visible', 'name: visible\ndescription: Visible\n');

    const kbs = await kbService.list();
    expect(kbs).toHaveLength(1);
    expect(kbs[0].name).toBe('visible');
  });

  it('gets a single KB by name', async () => {
    await createTestKb('test-kb', 'name: test-kb\ndescription: Test KB\naccess: read-write\n');

    const kb = await kbService.get('test-kb');
    expect(kb).not.toBeNull();
    expect(kb!.name).toBe('test-kb');
    expect(kb!.description).toBe('Test KB');
  });

  it('returns null for nonexistent KB', async () => {
    const kb = await kbService.get('nonexistent');
    expect(kb).toBeNull();
  });

  it('prevents path traversal in KB name', async () => {
    const kb = await kbService.get('../etc/passwd');
    expect(kb).toBeNull();
  });

  it('resolves KB path correctly', async () => {
    await createTestKb('my-kb', 'name: my-kb\ndescription: My KB\n');

    const resolved = await kbService.resolveKbPath('my-kb');
    expect(resolved).toBe(path.join(kbRoot, 'my-kb'));
  });

  it('returns null for nonexistent KB path', async () => {
    const resolved = await kbService.resolveKbPath('nonexistent');
    expect(resolved).toBeNull();
  });
});
