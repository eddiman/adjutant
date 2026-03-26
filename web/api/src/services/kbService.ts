/**
 * KB discovery service.
 *
 * Two modes of operation:
 * 1. Adjutant mode — reads from Adjutant's knowledge_bases/registry.yaml
 *    (when ADJUTANT_DIR / ADJ_DIR is set or ~/.adjutant exists)
 * 2. Standalone mode — scans kbRoot directory for subdirs with kb.yaml
 *    (legacy behavior, used when no Adjutant registry found)
 */

import fs from 'fs/promises';
import path from 'path';
import yaml from 'js-yaml';
import { configService } from './configService.js';
import { registryService } from './registryService.js';
import { KbYamlSchema } from '../types/kb.js';
import type { KbMeta } from '../types/kb.js';

class KbService {
  /**
   * Discover all KBs. Prefers Adjutant registry, falls back to standalone scan.
   */
  async list(): Promise<KbMeta[]> {
    // Try Adjutant registry first
    if (await registryService.isAvailable()) {
      return registryService.list();
    }

    // Fallback: standalone mode (scan kbRoot)
    return this.listStandalone();
  }

  /**
   * Get metadata for a single KB by name.
   */
  async get(name: string): Promise<KbMeta | null> {
    // Prevent path traversal
    if (name.includes('..') || name.includes('/') || name.includes('\\')) {
      return null;
    }

    if (await registryService.isAvailable()) {
      return registryService.get(name);
    }

    return this.getStandalone(name);
  }

  /**
   * Resolve a KB name to its absolute filesystem path.
   * Returns null if KB doesn't exist or path traversal detected.
   */
  async resolveKbPath(name: string): Promise<string | null> {
    if (name.includes('..') || name.includes('/') || name.includes('\\')) {
      return null;
    }

    if (await registryService.isAvailable()) {
      return registryService.resolveKbPath(name);
    }

    return this.resolveKbPathStandalone(name);
  }

  /**
   * Check whether we're running in Adjutant mode or standalone.
   */
  async getMode(): Promise<'adjutant' | 'standalone'> {
    return (await registryService.isAvailable()) ? 'adjutant' : 'standalone';
  }

  // === Standalone mode (legacy) ===

  private async listStandalone(): Promise<KbMeta[]> {
    const kbRoot = await configService.getKbRoot();
    if (!kbRoot) return [];

    const kbs: KbMeta[] = [];

    try {
      const entries = await fs.readdir(kbRoot, { withFileTypes: true });

      for (const entry of entries) {
        if (!entry.isDirectory() || entry.name.startsWith('.')) continue;

        const kbPath = path.join(kbRoot, entry.name);
        const meta = await this.parseKbYaml(kbPath);
        if (meta) {
          kbs.push(meta);
        }
      }
    } catch {
      return [];
    }

    return kbs.sort((a, b) => a.name.localeCompare(b.name));
  }

  private async getStandalone(name: string): Promise<KbMeta | null> {
    const kbRoot = await configService.getKbRoot();
    if (!kbRoot) return null;

    const kbPath = path.join(kbRoot, name);
    return this.parseKbYaml(kbPath);
  }

  private async resolveKbPathStandalone(name: string): Promise<string | null> {
    const kbRoot = await configService.getKbRoot();
    if (!kbRoot) return null;

    const kbPath = path.join(kbRoot, name);

    try {
      const yamlPath = path.join(kbPath, 'kb.yaml');
      await fs.access(yamlPath);
      return kbPath;
    } catch {
      return null;
    }
  }

  // === Private ===

  private async parseKbYaml(kbPath: string): Promise<KbMeta | null> {
    try {
      const yamlPath = path.join(kbPath, 'kb.yaml');
      const content = await fs.readFile(yamlPath, 'utf-8');
      const raw = yaml.load(content);
      const parsed = KbYamlSchema.parse(raw);

      return {
        name: parsed.name,
        description: parsed.description,
        path: kbPath,
        access: parsed.access,
        created: parsed.created,
      };
    } catch {
      return null;
    }
  }
}

export const kbService = new KbService();
