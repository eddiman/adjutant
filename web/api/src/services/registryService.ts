/**
 * Adjutant KB registry reader.
 *
 * Reads knowledge_bases/registry.yaml from the Adjutant directory to discover
 * KBs. This is an alternative to the standalone configService-based discovery.
 *
 * When ADJUTANT_DIR is set, the web dashboard reads KBs directly from Adjutant's
 * registry instead of scanning a kbRoot directory. This ensures the dashboard
 * stays in sync with Adjutant's KB list and respects access levels.
 *
 * Registry format (pure YAML, no pyyaml at runtime in Adjutant):
 *   knowledge_bases:
 *     - name: "my-kb"
 *       description: "..."
 *       path: "/absolute/path"
 *       model: "anthropic/claude-sonnet-4-6"
 *       access: "read-write"
 *       created: "2026-01-15"
 */

import fs from 'fs/promises';
import path from 'path';
import yaml from 'js-yaml';
import type { KbMeta } from '../types/kb.js';

interface RegistryEntry {
  name: string;
  description: string;
  path: string;
  model?: string;
  access?: 'read-only' | 'read-write';
  created?: string;
}

interface Registry {
  knowledge_bases: RegistryEntry[];
}

class RegistryService {
  private adjutantDir: string | null = null;
  private disabled = false;

  /**
   * Resolve the Adjutant directory. Checks:
   * 1. ADJUTANT_DIR env var (set by Adjutant or user)
   * 2. ADJ_DIR env var (set by Adjutant core/paths.py at runtime)
   * 3. ~/.adjutant (default fallback)
   *
   * A candidate is valid if it contains either:
   * - knowledge_bases/registry.yaml (KB registry)
   * - adjutant.yaml (Adjutant config)
   *
   * Returns null if none exist.
   */
  async resolveAdjutantDir(): Promise<string | null> {
    if (this.disabled) return null;
    if (this.adjutantDir !== null) return this.adjutantDir;

    const candidates: string[] = [];

    // Explicit env vars take priority
    if (process.env.ADJUTANT_DIR) candidates.push(process.env.ADJUTANT_DIR);
    if (process.env.ADJ_DIR) candidates.push(process.env.ADJ_DIR);

    // In monorepo layout, the repo root is four levels up from this file
    // Only try this if no explicit env var is set (avoids test interference)
    if (!process.env.ADJUTANT_DIR && !process.env.ADJ_DIR) {
      const monorepoRoot = path.resolve(__dirname, '..', '..', '..', '..');
      candidates.push(monorepoRoot);
    }

    candidates.push(path.join(process.env.HOME || '', '.adjutant'));

    for (const candidate of candidates) {
      // Check for registry.yaml (KB registry) OR adjutant.yaml (config)
      const probes = [
        path.join(candidate, 'knowledge_bases', 'registry.yaml'),
        path.join(candidate, 'adjutant.yaml'),
      ];

      for (const probe of probes) {
        try {
          await fs.access(probe);
          this.adjutantDir = candidate;
          return candidate;
        } catch {
          // Not found, try next probe
        }
      }
    }

    this.adjutantDir = null;
    return null;
  }

  /**
   * Check if Adjutant integration is available.
   */
  async isAvailable(): Promise<boolean> {
    return (await this.resolveAdjutantDir()) !== null;
  }

  /**
   * List all KBs from Adjutant's registry.
   */
  async list(): Promise<KbMeta[]> {
    const adjDir = await this.resolveAdjutantDir();
    if (!adjDir) return [];

    try {
      const registryPath = path.join(adjDir, 'knowledge_bases', 'registry.yaml');
      const content = await fs.readFile(registryPath, 'utf-8');
      const registry = yaml.load(content) as Registry;

      if (!registry?.knowledge_bases || !Array.isArray(registry.knowledge_bases)) {
        return [];
      }

      const kbs: KbMeta[] = [];
      for (const entry of registry.knowledge_bases) {
        // Validate the KB path actually exists and has kb.yaml
        try {
          await fs.access(path.join(entry.path, 'kb.yaml'));
          kbs.push({
            name: entry.name,
            description: entry.description || '',
            path: entry.path,
            access: entry.access || 'read-only',
            created: entry.created,
          });
        } catch {
          // KB path doesn't exist or isn't accessible — skip silently
        }
      }

      return kbs.sort((a, b) => a.name.localeCompare(b.name));
    } catch (error) {
      console.error('Failed to read Adjutant registry:', error);
      return [];
    }
  }

  /**
   * Get a single KB by name.
   */
  async get(name: string): Promise<KbMeta | null> {
    const kbs = await this.list();
    return kbs.find(kb => kb.name === name) || null;
  }

  /**
   * Resolve a KB name to its absolute path.
   */
  async resolveKbPath(name: string): Promise<string | null> {
    const kb = await this.get(name);
    return kb?.path || null;
  }

  /** Clear cached directory (for testing). */
  clearCache(): void {
    this.adjutantDir = null;
    this.disabled = true;
  }

  /** Re-enable resolution (for testing). */
  enable(): void {
    this.disabled = false;
  }
}

export const registryService = new RegistryService();
