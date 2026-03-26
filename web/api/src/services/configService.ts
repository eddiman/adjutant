import fs from 'fs/promises';
import path from 'path';
import { config } from '../config.js';
import type { AppConfig } from '../types/config.js';
import { AppConfigSchema } from '../types/config.js';

class ConfigService {
  private cache: AppConfig | null = null;

  async init(): Promise<void> {
    await fs.mkdir(config.configDir, { recursive: true });
  }

  async get(): Promise<AppConfig> {
    if (this.cache) return this.cache;

    try {
      const content = await fs.readFile(config.configFile, 'utf-8');
      const parsed = AppConfigSchema.parse(JSON.parse(content));
      this.cache = parsed;
      return parsed;
    } catch {
      // No config file or invalid — return defaults
      return {};
    }
  }

  async update(updates: Partial<AppConfig>): Promise<AppConfig> {
    const current = await this.get();
    const merged: AppConfig = { ...current, ...updates };

    // Validate kbRoot if provided
    if (merged.kbRoot) {
      const resolvedPath = path.isAbsolute(merged.kbRoot)
        ? merged.kbRoot
        : path.resolve(process.cwd(), merged.kbRoot);
      merged.kbRoot = resolvedPath;

      // Validate directory exists
      try {
        const stat = await fs.stat(resolvedPath);
        if (!stat.isDirectory()) {
          throw new Error(`Path is not a directory: ${resolvedPath}`);
        }
      } catch (err) {
        if (err instanceof Error && err.message.startsWith('Path is not')) {
          throw err;
        }
        throw new Error(`Directory does not exist: ${resolvedPath}`);
      }

      // Validate it contains at least one KB (directory with kb.yaml)
      const entries = await fs.readdir(resolvedPath, { withFileTypes: true });
      let hasKb = false;
      for (const entry of entries) {
        if (!entry.isDirectory()) continue;
        try {
          await fs.access(path.join(resolvedPath, entry.name, 'kb.yaml'));
          hasKb = true;
          break;
        } catch {
          // Not a KB directory
        }
      }
      if (!hasKb) {
        throw new Error(`No knowledge bases found in ${resolvedPath} (no subdirectories with kb.yaml)`);
      }
    }

    await fs.mkdir(config.configDir, { recursive: true });
    await fs.writeFile(config.configFile, JSON.stringify(merged, null, 2), 'utf-8');
    this.cache = merged;
    return merged;
  }

  async getKbRoot(): Promise<string | null> {
    const appConfig = await this.get();
    return appConfig.kbRoot || null;
  }

  // Clear cache (useful for testing)
  clearCache(): void {
    this.cache = null;
  }
}

export const configService = new ConfigService();
