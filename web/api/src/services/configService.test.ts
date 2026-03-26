import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import fs from 'fs/promises';
import path from 'path';
import os from 'os';
import { configService } from './configService.js';
import { config } from '../config.js';

// Use a temp dir for testing so we don't touch the real config
let originalConfigDir: string;
let originalConfigFile: string;
let tempDir: string;

beforeEach(async () => {
  tempDir = await fs.mkdtemp(path.join(os.tmpdir(), 'adjutant-web-test-config-'));
  originalConfigDir = config.configDir;
  originalConfigFile = config.configFile;

  // Monkey-patch config to use temp dir
  Object.defineProperty(config, 'configDir', { value: tempDir, writable: true, configurable: true });
  Object.defineProperty(config, 'configFile', {
    get: () => path.join(tempDir, 'config.json'),
    configurable: true,
  });

  configService.clearCache();
});

afterEach(async () => {
  Object.defineProperty(config, 'configDir', { value: originalConfigDir, writable: true, configurable: true });
  Object.defineProperty(config, 'configFile', {
    get: () => path.join(originalConfigDir, 'config.json'),
    configurable: true,
  });

  await fs.rm(tempDir, { recursive: true, force: true });
});

describe('ConfigService', () => {
  it('returns empty config when no config file exists', async () => {
    const appConfig = await configService.get();
    expect(appConfig).toEqual({});
  });

  it('reads kbRoot from config file', async () => {
    await fs.writeFile(
      path.join(tempDir, 'config.json'),
      JSON.stringify({ kbRoot: '/some/path' }),
      'utf-8',
    );
    configService.clearCache();

    const appConfig = await configService.get();
    expect(appConfig.kbRoot).toBe('/some/path');
  });

  it('validates that kbRoot directory must exist', async () => {
    await expect(
      configService.update({ kbRoot: '/nonexistent/path/that/does/not/exist' }),
    ).rejects.toThrow('Directory does not exist');
  });

  it('validates that kbRoot must contain at least one KB', async () => {
    // Create a temp dir with no kb.yaml subdirectories
    const emptyRoot = await fs.mkdtemp(path.join(os.tmpdir(), 'adjutant-web-test-empty-'));
    await fs.mkdir(path.join(emptyRoot, 'some-folder'));

    try {
      await expect(
        configService.update({ kbRoot: emptyRoot }),
      ).rejects.toThrow('No knowledge bases found');
    } finally {
      await fs.rm(emptyRoot, { recursive: true, force: true });
    }
  });

  it('accepts a valid kbRoot with a KB directory', async () => {
    const validRoot = await fs.mkdtemp(path.join(os.tmpdir(), 'adjutant-web-test-valid-'));
    const kbDir = path.join(validRoot, 'test-kb');
    await fs.mkdir(kbDir);
    await fs.writeFile(
      path.join(kbDir, 'kb.yaml'),
      'name: test-kb\ndescription: test\naccess: read-only\n',
      'utf-8',
    );

    try {
      const result = await configService.update({ kbRoot: validRoot });
      expect(result.kbRoot).toBe(validRoot);

      // Verify it was persisted
      configService.clearCache();
      const reread = await configService.get();
      expect(reread.kbRoot).toBe(validRoot);
    } finally {
      await fs.rm(validRoot, { recursive: true, force: true });
    }
  });

  it('getKbRoot returns null when not configured', async () => {
    const root = await configService.getKbRoot();
    expect(root).toBeNull();
  });
});
